# fuxi (Xiaomi 13 / SM8550) 上跑 XNU / iOS —— 阶段总结

> 状态时间点：预链接（prelink）路径已在 QEMU 打通到 `kdp_core`，真机仍在
> `XNU jumping` 处无输出。本文记录全部问题、已解决项、当前卡点与后续思路。

---

## 1. 总体路线

```
fastboot boot.img
   └─ ABL 载入（要求 kernel 区内含 DTB）
        └─ loader-shim（裸机，不用 UEFI）
             ├─ 解析 payload（FUXIXNU 格式：段表 + ADT + 命令行）
             ├─ 按段表把每个段平铺拷贝到 phys_base + (va - virt_base)
             ├─ 修正 ADT（dram-base/size、framebuffer、GIC、vtimer）
             └─ 跳 XNU 入口（PA 形式）
                  └─ XNU：start.s → arm_vm_init → pmap → kalloc → zone → bsd_init
                       └─ KLDBootstrap 读 __PRELINK_INFO → 加载 kext → 找根卷 → 用户态
```

关键取舍：**不用 UEFI**。fuxi 的 UEFI 路线死过一轮（GOP 在真机不可见、EDK2 移植成本高），
裸机 shim 更可控。

---

## 2. 已解决的问题（含根因）

### 2.1 引导与镜像

| 问题 | 根因 | 解决 |
|---|---|---|
| ABL 拒绝我们的 boot.img，直接回 fastboot | kernel 区必须包含 DTB，且 `kernel_size` 覆盖 [gzip 内核 + DTB + 填充] | `mkshim_bootimg.py` 把 DTB 追加在 kernel 区内；`patch_boot_kernel.py` 原地替换内核并保留 DTB 尾部 |
| UEFI GOP 报告 0xB0000000，真机屏幕无输出 | fuxi 的 GOP 在真机不可见 | 改用 ABL splash framebuffer，实测 **0xB8000000**（`splash_region`，0x2B00000） |
| 裸机访问 ≥4GB 物理地址触发外部中止（ESR 0x96000010，FAR 0x101004000） | Gunyah/stage-2 只映射低 4GB | 内核窗口下移到低 DRAM（`FUXI_LOW_PHYS` 0x90000000 起） |
| payload 与内核内存重叠 | 窗口把 shim 自身（~0xA8080000）也包进去了 | 缩小内核窗口并在 loader 里加重叠检查 |

### 2.2 GIC / 中断（真机第一次出日志的关键）

| 问题 | 根因 | 解决 |
|---|---|---|
| `pe_init_fiq` panic：GICR 线性扫描越界 | 用 MPIDX 扫描而不是 Aff0 直接索引 | `find_gicr_pe_base` 改为按 Aff0 直接算索引 |
| GIC 地址算错一倍 | ADT 里 gic reg 必须**相对 /soc**，XNU 会再加 `soc_base_phys=0x01000000` | `adt_fix_fuxi.py` 写成 `0x16100000/0x16180000` |
| `GICR_IGROUPR0` 偏移双加 | XNU 头里的 `GICR_IGROUPR0 = 0x10080` 已含 SGI 帧偏移，再 `+0x10000` 就错了 | 去掉额外偏移 |
| GICR 每核大小不对 | 实际 `GICR_PE_SIZE = 0x40000` | 在板级头里改正 |
| vtimer 中断号 | fuxi 是 INTID **19** | ADT 与板级配置都写 19 |

### 2.3 构建系统 / CI（最隐蔽的一类）

| 问题 | 根因 | 解决 |
|---|---|---|
| 37 处改动**从未被编译** | 板级宏用的是 `-DARM64_BOARD_CONFIG_FUXI`，我们写的是 `#if defined(FUXI)` | 全部改成 `defined(ARM64_BOARD_CONFIG_FUXI)` |
| 某个补丁静默不生效（0017 丢失） | 补丁冲突时 `git apply` 失败，脚本继续跑 | 把 0017 的 hunk 合并进 0004，并在生成器里校验 `git apply --check` |
| CI 立刻红叉 | `build-xnu.yml` 里重复的 `concurrency:` 键 | 删掉重复键 |
| CI 推回仓库被拒 | 与自动提交竞争 | 自动提交改 rebase + 重试循环 |
| `ld: Undefined symbols: _fuxi_early_string` | 该函数是 `static` | 改用导出的 `fuxi_early_putc` |
| `bootstrap.cpp` 编译失败（libsa 没有 `kprintf`） | libsa 是 freestanding | 打点改到 `OSKext.cpp` |

### 2.4 早期调试可见性

| 问题 | 根因 | 解决 |
|---|---|---|
| panic 发生在控制台初始化前，屏幕全黑 | 无输出通道 | 自建 `fuxi_early.c`：直接写 0xB8000000 的早期控制台 + `fuxi_early_panic()` 挂钩 `panic_trap_to_debugger` |
| TTBR0 关闭后早期控制台失效 | 物理地址映射随 bootstrap 页表消失 | 补丁 0012：在 `VM_MIN_KERNEL_ADDRESS + 32MB` 建常驻 framebuffer 别名并 relocate |
| QEMU 里软件断点不可用 | 我们这套 stub/内核组合下断点不生效 | 改用「跑完采样 PC + 从内存读 panic 字符串 + 帧指针回溯」 |

### 2.5 内核打包（chained fixups）

| 问题 | 根因 | 解决 |
|---|---|---|
| 内核是 PIE + `LC_DYLD_CHAINED_FIXUPS`，没人解析指针 | 没有 kmutil/iBoot | `mkpayload_fuxi.py` 自己走链，把每个指针重写成 unslid 目标 |

### 2.6 Apple kext 预链接（本轮重点）

目标：把 Apple kernelcache 里的 APFS 及其依赖注入我们的内核。

| 问题 | 根因 | 解决 |
|---|---|---|
| 组件绑定到我们内核时缺 1 个符号 `_vfs_getvfs_with_vfsops` | 内核未导出该函数 | 补丁 0029 加兼容实现，符号覆盖达 100% |
| 组件在 Apple 布局里分散 45MB，而 kext 区只有 16MB | 保留 Apple 相对地址 | **紧凑重排**：容器内按 VA 顺序打包，只需 2.5MB |
| 指针指向组件内部时错位 | 重排改变了地址 | 建 old_va→new_va 映射，站点与目标都走映射（12,136 处全部成功） |
| 内核不认识组件 | 内核对组件的映射看的是**内核自己的 Mach-O 段表** | 就地修改 payload 里 Mach-O 的 `__PRELINK_TEXT/__PLK_TEXT_EXEC/__PLK_DATA_CONST/__PRELINK_DATA/__PRELINK_INFO` 段 |
| 内核仍不认为自己是预链接的 | 判断用的是 `__PRELINK_INFO/__info` **section** 大小，只改段没用 | 同时改段内 section 的 addr/size |
| panic `zone_require_ro ... addr: 0`（早期，VM bootstrap 后） | `kalloc_type_view_parse`（KCGEN 分支）遍历 `__PRELINK_TEXT` 里每个 kext，读其 `__DATA_CONST.__kalloc_type` 节地址；我们注入的 kext 头里仍是 Apple 的 `0xfffffff0...` → 访问未映射地址 | 重写每个组件 Mach-O 的段/节地址（`component_headers.py`） |
| panic `memcmp_zero_ptr_aligned(...) == 0` | XNU 按「每个 kext 的 `__TEXT.filesize` 对齐」跳跃，我们的容器尾部有残留数据 | 按 XNU 的遍历模型重建容器：只放 `32+sizeofcmds` 的头，其余清零；`LC_SEGMENT_SPLIT_INFO` 常量必须是 `0x1e`（不是 0x1d） |
| `OSUnserializeXML: syntax error near Line 1/3` | ①`OSBundleLibraries` 子字典生成错（空 `<dict />`、键挂错层级）②多余 XML 声明头（Apple 的 `__info` 直接以 `<dict>` 开头） | 重写 XML 生成器，去掉声明头 |
| 真机刷入后**卡在红底 `XNU jumping`**（当前） | 见第 3 节 | 未解决 |

### 2.7 一次重要的误判（务必记住）

中途所有「改了 `virt_base` 就 panic」的结论**都是错的**。真实原因是 QEMU 测试时 payload 用了
**fuxi.adt**（GIC 在 0x17180000，QEMU 不存在）→ 内核在 `pe_init_fiq` 等 GICR 唤醒超时 →
panic 文本是 `core %u timed out waiting for redistributor to wake up`。

**规矩：QEMU 用 `qemu.adt`，真机用 `fuxi.adt`。**

---

## 3. 当前卡点：真机无输出

### 现象

```
屏幕：红底 "XNU jumping"（这是我们 shim 打印的最后一行）
      然后没有任何内核输出
```

同一份 payload 在 QEMU（qemu.adt）能跑到 `kdp_core zlib memory 0x6000`（正常 idle）。

### 已排除

| 假设 | 证据 |
|---|---|
| 镜像打包错（缺 DTB 等） | shim 已经跑起来并打印到 jumping，说明 boot.img 结构没问题 |
| 内核本身在真机不能跑 | 早期版本（kernel 20/21，无预链接段）在真机能出完整日志到 `kdp_core` |
| 挪 `__TEXT` 导致 | 已回退，仍无输出 |
| 只是预链接数据错 | 带预链接段的 QEMU payload 能启动；真机不能 → 差异在 bootloader/内存布局 |

### 高度可疑点

```
① virt_base 变了
   无预链接段时：virt_base = __TEXT 所在 32MB 块 = 0xfffffe0006000000
   有预链接段时：virt_base = 最低段（__PRELINK_TEXT 0x4004000）对齐 = 0xfffffe0004000000
   → 内核被搬到了 phys_base + 0x4000 而不是 +0x1004000
   → start.s / arm_vm_init 对「块映射起点」的假设可能只在 0x6000000 成立

② 真机 phys_base = 0x90000000，QEMU phys_base = 0x100000000
   两边低地址段的对齐关系不同，真机上可能出现 pad 区/页表与段重叠

③ 真机是 4GB 窗口（Gunyah），内核 + 组件跨度 64MB 后
   boot_args/topOfKernelData 与 ADT 的 dram-size 可能需要同步调整
```

### 建议的下一步（按性价比）

1. **让 shim 把关键值打到屏幕上**（不需要内核构建）：
   `virtBase / physBase / entry_va / entry_pa / kernel_end / 段数 / 每段 (va,pa,size)`。
   只要看到这些，就能判断是"内核没跑"还是"跑了但没输出"。
2. **真机试"无预链接段 + 组件数据也在 payload 里但不登记到 Mach-O"**：
   验证「payload 变大」本身是否影响真机（排除 4GB 窗口/拷贝问题）。
3. **把 `virt_base` 强制回 0x6000000，组件放到 `[0x6000000, __TEXT)` 里**
   （重排后只占 2.5MB，16MB 区够），这样 virt_base 与"能工作的版本"一致。
   —— 这是我最推荐的一条：**保持一切与已验证能跑的版本一致，只增加段**。
4. 若仍不行，考虑在 `arm_vm_init` 里加真机专用兜底（把组件段排除在
   `segLOWESTTEXT` / 静态区计算之外），但那要内核构建。
5. 备选路线：走 UniXNU 的 DarwinBoot（UEFI + FAT payload + GOP），
   代价是重做显示与引导；收益是内核加载/滑移逻辑有成熟参考。

---

## 4. 距离"用户态"还差什么

| # | 缺口 | 说明 | 谁 |
|---|---|---|---|
| 1 | 真机能输出 | 当前卡点 | 我（shim 侧诊断，无需内核） |
| 2 | kext 加载跑完 | QEMU 侧已能解析清单；待真机验证 | 我 |
| 3 | 内核里的 UFS 块设备 | 现在只有 shim 的只读探测；要读 userdata 必须进内核（移植 UniXNU `NativeUfs`） | 我 |
| 4 | 根卷接线 | ADT 的 root volume UUID / Cryptex 配置 / trust cache 注入 | 我 |
| 5 | 用户态内容 | iOS 的 userdata / SystemOS 卷 | **你**（IPSW 提取） |
| 6 | 显示/触控驱动 | 用户态跑起来之后：GOP 式线性帧缓冲 + GENI SPI/I2C + GT9916 + HID | 我 |

---

## 5. 关键参数速查

```
SoC / 机型            SM8550 kalama / Xiaomi 13 (fuxi)，A76+A55，无 PAC（arm64）
framebuffer           0xB8000000（ABL splash），1080x2400，stride 4320
GICD                  0x17100000 (+0x10000)
GICR                  0x17180000 (+0x200000)，PE_SIZE 0x40000
vtimer INTID          19
内核窗口（低 DRAM）     phys_base 0x90000000，size 0x17000000
内核 __TEXT           0xfffffe0007004000（朴素布局）
__PRELINK_TEXT 占位   0xfffffe0004004000
ADT GIC reg           相对 /soc：0x16100000 / 0x16180000
页大小                 16K（__ARM_16K_PG__）
内核源码版本           xnu-8796.141.3（CI），IPSW 为 16.7.16 / xnu-8796.142.1
```

---

## 6. 工具清单（`tools/`）

| 文件 | 作用 |
|---|---|
| `mkpayload_fuxi.py` | 内核 Mach-O → FUXIXNU payload（解 chained fixups） |
| `mkadt.py` / `adt_fix_fuxi.py` | 生成/修正 fuxi 的 ADT |
| `mkshim_bootimg.py` / `patch_boot_kernel.py` | 打包 boot.img（含 DTB） |
| `replace_shim_payload.py` / `make_final_image.py` | 替换 shim 内嵌 payload（支持 `USE_PAYLOAD`） |
| `prelink_try2.py` | 容错解析 Apple kernelcache、`plan()` 选组件/算绑定 |
| `prelink_payload5.py` | **主入口**：组件重排 + 段表改写 + 预链接清单 + 指针重绑 |
| `component_headers.py` | 重写组件 Mach-O 的段/节地址、按 stride 清零 |
| `prelink_text_rebuild.py` | 按 XNU 遍历模型重建 `__PRELINK_TEXT` |
| `qemu_fuxi.py` | QEMU 跑 payload、采样 PC、截屏 |
| `dump_panic2.py` / `panic_backtrace.py` | 从内存读 panic 字符串、帧指针回溯调用栈 |

---

## 7. 仓库状态

```
分支 main，远程 github.com/Xyvern08371/ios-on-fuxi
补丁：0004（板级+DT+GIC）、0010（早期帧缓冲）、0012（TTBR0 后保留）、
      0027（AppleKeyStore 假实现）、0028（启动打点）、0029（vfs 兼容符号）、
      0031（kext 数量打印）、0032（kext 加载打点）、0033（slide/段地址打印）
0030（挪 __TEXT）已回退
```

## 8. 如何恢复手机

```powershell
cd E:\ios-on-fuxi
$fb = "scripts\adb-platform-tools-latest-windows\platform-tools\fastboot.exe"
& $fb flash boot_a E:\fuxi\boot.img
& $fb flash boot_b E:\fuxi\boot.img
& $fb reboot
# 或直接跑 scripts\restore_pe.bat
```
