# fuxi (Xiaomi 13) XNU 移植状态

> 最后更新：真机已达 M7；QEMU 可复现到内核 idle

## 里程碑

| # | 目标 | 状态 |
|---|---|---|
| M0 | 工具链与骨架 | ✅ |
| M0.5 | 固件解析 + 真机设备树 | ✅ |
| M1 | 真机运行我们的代码（EL1 / 帧缓冲） | ✅ |
| M2 | `ExitBootServices` 成功 | ✅ |
| M3 | 裸机自绘文字 | ✅ |
| M4 | 内核交接 | ✅ |
| M5 | 独立内核运行 | ✅ |
| M6 | 自建 XNU 编译 | ✅ |
| **M7** | **XNU 在真机产生可见输出** | ✅ **达成（真机打印出 panic 现场）** |
| M8 | 平台层移植（显示/中断/存储） | 🔄 进行中 |

## 路线切换记录

- **UEFI 路线**：验证到极限。可以关 MMU、入口代码一致，但关 MMU 后写显存不生效 → 放弃
- **裸机 shim 路线**（当前）：直接由 ABL 启动我们的裸机加载器，接管 EL1、MMU 关闭状态

## 真机验证过的关键事实

### boot.img 格式（决定 ABL 是否接受）

```
[header 2048][ gzip 内核 ][ DTB ][ 填充 ]
             └── kernel_size 覆盖这一段 ──┘
```

- DTB 必须在 kernel 段内、并且算进 `kernel_size`，**缺了 ABL 直接拒绝启动**
- header v1 / page 2048 / kernel_addr 0x10000000
- `id` = SHA1(kernel 段 + ramdisk)
- 打包：`tools/mkshim_bootimg.py`（自动拼 DTB）
- 或原地换内核：`tools/patch_boot_kernel.py`

### 裸机内存

- **4GB 以上不可访问**：同步外部中止（ESR `0x96000010`）
- 内核窗口一度设为 `0x90000000 + 0x30000000`（覆盖帧缓冲但含 mpss 保留区），
  又缩到 64MB（避开保留区但盖不到帧缓冲）——**这块还没定论**
- shim 自身加载在 `0xA8080000` 附近，payload 在其后 0x2C000 处

### 帧缓冲

| 阶段 | 地址 |
|---|---|
| UEFI GOP 报的 | `0xB0000000`（裸机不可见） |
| **裸机真正可见** | **`0xB8000000`**（DT `splash_region`） |

ADT `fuxi-fbcon`、内核早期标记、boot_args Video 全部用 `0xB8000000`。

### GIC（本轮重点）

| 项 | 正确值 | 备注 |
|---|---|---|
| GICD | `0x17100000`，0x10000 | |
| GICR | `0x17180000`，0x200000 | 8 核 × 0x40000 |
| `GICR_PE_SIZE` | **0x40000** | fuxi；sweet 是 0x20000 |
| ADT 里 gic 的 reg | **相对 /soc**：`0x16100000` / `0x16180000` | XNU 会加 `soc_base_phys`(0x01000000) |
| `GICR_IGROUPR0` | **0x10080**（XNU 头已含 SGI 帧偏移） | **不要再 +0x10000** |
| 虚拟定时器 INTID | **19** | QEMU/sweet 是 27 |

`find_gicr_pe_base()` 的线性扫描会踩出 GICR 区间 → 已改为按 `MPIDR.Aff0` 直接索引。

实测（QEMU，k19）：

```
FUXI GICR: gicd=fffffe000b3c8000 gicr=fffffe000b3d0000 size=200000
           pe=fffffe000b3d0000 IGROUPR0=10080 WAKER=14
```

### 编译宏门控（隐蔽的杀手）

构建**只定义** `-DARM64_BOARD_CONFIG_FUXI`，从不定义 `-DFUXI`。
补丁里所有 `#if defined(FUXI)` 恒为假 → 37 处平台代码从未编进去，跑的是 Apple 原始实现。
已全部改成 `defined(ARM64_BOARD_CONFIG_FUXI)`。

### 补丁冲突会被整体跳过

`0017` 因与 `0004` 同改 `pe_fiq.c` 而被**整体跳过**（连 `sleh.c` 的改动也没生效）。
已把 0017 的 `pe_fiq.c` 部分合并进 0004。

## 当前卡点

- **真机**：最后刷的是 k16（GICR 偏移仍错）。**k19 已修正，待刷**。
- **QEMU**：内核跑到 `kdp_core zlib memory 0x6000` 后进入 idle，无新日志。
  - `startup_debug=1` 未产生 `kernel_bootstrap:` 日志
  - gdbstub 中断后寄存器读到无效值（pc=0x200），断点不命中 → 该环境不可靠

## 工具

| 工具 | 用途 |
|---|---|
| `tools/qemu_fuxi.py` | QEMU 跑内核（`--smp` / `--samples` / fbgrab） |
| `tools/qemu_shim.py` | QEMU 跑 shim 本身 |
| `tools/gdbstub.py` | 最小 GDB 协议客户端 |
| `tools/gdb_probe.py` | 断点探测（本环境不稳定） |
| `tools/backtrace.py` | 帧指针回溯（本环境不可靠） |
| `tools/mkshim_bootimg.py` | 打 boot.img（gzip + DTB） |
| `tools/patch_boot_kernel.py` | 原地换内核（保留 DTB） |
| `tools/replace_shim_payload.py` | 换 shim 内嵌 payload |
| `tools/adt_fix_fuxi.py` | kalama.adt → fuxi.adt |
| `tools/mkpayload_fuxi.py` | 生成 FUXIXNU payload |
| `tools/fix_patch_counts.py` | 手工改 hunk 后重算行数 |

## 下一步

1. 手机连上后刷 **k19**（GICR 偏移已修正），预期越过 `pe_init_fiq`
2. 若真机能到 `VM bootstrap done`，下一个目标是 `bsd_init`
3. `bsd_init` 之后需要 rootfs（用户负责）；内核侧要处理 SEP / AppleKeyStore
   （ios-sweet 的 `0038-sweet-applekeystore.patch` 尚未导入）
4. QEMU 侧：把 GIC 改成 QEMU 可用的地址（`0x08000000` 在 QEMU 是 pflash，需换 ADT）
   才能让 QEMU 真正验证中断/定时器
