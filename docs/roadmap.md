# 路线图与进度

原则：每个里程碑都有**可验证的验收标准**，做不到就停在那一步，不往下堆假设。

## 里程碑总览

| # | 目标 | 验收标准 | 状态 |
|---|---|---|---|
| **M0** | 工具链与骨架 | `appledt` 自测全过；能合成合法 DTB；loader 就位 | ✅ 已完成 |
| **M0.5** | 固件解析 + 真机设备树 | 从 vendor_boot/dtbo 抽出 DT 并合并成 4852 节点，校验通过 | ✅ 已完成 |
| **M1** | 真机运行我们的代码 | 屏幕上打印出 `CurrentEL=EL1`、GOP 参数、帧缓冲地址 | ✅ 已完成（2026-10-18） |
| **M2** | 退出 Boot Services | `ExitBootServices` 返回成功，退出后仍能写显存 | ✅ 已完成（2026-10-18，蓝屏验证） |
| **M3** | 裸机自绘文字 | 不依赖 UEFI 控制台，用自带点阵字体在屏幕上画出信息 | ✅ 已完成（2026-10-18） |
| **M4** | 内核交接 | 关中断 / 换栈 / `x0`=设备树，读到 DTB 魔数 `D00DFEED` | ✅ 已完成（2026-10-18） |
| **M5** | 独立内核运行 | 独立编译的内核在真机上显示 `KERNEL RUNNING` | ✅ 已完成（2026-10-18） |
| **M6** | 自建 XNU 能编译并链接 | 用开源 darwin-xnu 源码编出 arm64 内核镜像 | ✅ 已完成（`kernel.development.fuxi` 16.4MB） |
| **M7** | XNU 在真机上产生可见输出 | 屏幕或串口出现 XNU 自己的输出（哪怕是 panic） | 🟡 **进行中**：加载器全链路打通，内核已执行到 `_start`，卡在开 MMU |
| **M8** | 平台层移植 | XNU 在 fuxi 上推进到设备初始化之后 | ⬜ 未知领域 |

## M1–M5 的实测结论（全部真机验证）

| 项 | 值 |
|---|---|
| CurrentEL | **EL1**（跳内核不需要 EL2 降级） |
| 帧缓冲 | `0xB0000000`，1080×2400，`PixelFormat=1`(BGRX) |
| 真实行跨距 | **1080**（GOP 报的 `PixelsPerScanLine=1000` 是错的，用 `FBSZ/4/H` 反推） |
| 内存图 | 102 条描述符，48 字节/条，9 条带 runtime 属性 |
| 设备树 | 固件**不**把它放进 EFI 配置表 → 已把真机导出的 818KB DT 编进驱动 |
| `boot_args` | 与 xnu-8792 的 `pexpert/arm64/boot.h` 逐字段一致 |

## M6 当前进度（自建 XNU，只用开源代码）

目标：**用 apple-oss-distributions/xnu 源码编出 arm64 内核**，不碰任何 Apple 加密固件。

### 已解决（按出现顺序）

| # | 问题 | 修法 |
|---|---|---|
| 1 | Xcode 15 的 SDK 缺 `availability.pl` | 造一个最小替身 |
| 2 | clang 15 把 80 处警告当错误 | 构建前从 `makedefs` 删掉 `-Werror` |
| 3 | 缺 `os/firehose_buffer_private.h`（Apple 私有头） | 用 `xnu-stubs/` 里的最小替身，只补常量与空实现 |
| 4 | 链接要 `libVMAPPLE.os.RELEASE.a`、`libfirehose_kernel.a`（Apple 私有库） | 造空静态库（`/System` 只读，路径改到 `/tmp`） |

**至此所有源码编译通过**，进入链接阶段。

### 当前卡点

```
ld: entry point (__start) undefined. for architecture arm64e
```

排查结论：

- `osfmk/conf/files.arm64` 里是 `osfmk/arm64/start.s  optional  nos_arm_asm`
- `nos_arm_asm` 是"不要 ARM 汇编"标记，当前构建（VMAPPLE）下打开 → `start.s` 不参与汇编
- 已尝试：把 `nos_arm_asm` 换成 `arm64`（只对树里真实存在的文件改），config 不再报错，但 `start.o` 仍未生成

### 已确认与已尝试（2026-10-18 夜）

| 步骤 | 结果 |
|---|---|
| `optional nos_arm_asm` → `standard` | ✅ config 选中了，出现 `AS start.o` |
| 汇编时报缺 `<arm64/tunables/tunables.s>` | ❌ 汇编器的 `-I` 里没有 `osfmk` |
| 往 `makedefs/MakeInc.def|.cmd` 追加 `ASFLAGS +=` | ❌ 被生成 Makefile 里的 `ASFLAGS =` 覆盖 |
| 两段式：第一遍编完后，把 `ASFLAGS +=` 追加到**生成的 Makefile** 末尾再增量重编 | ❌ 仍然缺头文件 |

说明：`osfmk/RELEASE/Makefile` 里 `start.o` 的编译规则**不使用 `ASFLAGS`** 这个变量
（或用了别的变量/内联参数），所以追加 `ASFLAGS` 无效。

### 明天的三条备选（按可靠性排序）

**A. 手动汇编 start.o，再骗过链接**
```bash
# 用和 bcopy.o 完全相同的命令汇编 start.s（从 Makefile 里抄）
as -I<osfmk> -I<...> -o start.o osfmk/arm64/start.s
# 然后让链接器用到它（改 LDFILELIST 或直接塞进链接参数）
```
最可靠：绕开 config 与 Makefile 的所有规则。

**B. 把缺的头文件放到汇编器能找到的地方**
把 `osfmk/arm64/tunables/tunables.s`、`assym.s` 复制/软链到构建目录，
让相对路径能被找到（需先确认 as 的搜索规则）。

**C. 打印 start.o 的真实编译规则**
`grep -A5 "^start.o:" BUILD/obj/*/osfmk/RELEASE/Makefile`
看清它到底用哪个变量传 `-I`，再精确注入。

### 后续（M7/M8）已知难点

- `start.s` 内有 A 系列 CPU 的 MAIR/TTBR/系统寄存器硬编码 → 运行期需要改
- XNU 的 PE 平台层（`pexpert`）假定 iBoot 提供显示/电源/存储驱动 → 真机上没有，需要自己写
- 没有前例可参考：现存的 QEMU-iOS 项目是在**模拟器层面** hook，不是真机移植

## CI 踩过的坑（UEFI 固件部分）

| 报错 | 原因 | 修法 |
|---|---|---|
| `could not read Username ... subhook` | edk2 子模块指向已删除仓库 | 把该子模块设为 `update none` |
| `library class [DevicePathLib] is not found` | `UefiLib` 的传递依赖 | 不用 UefiLib，改 PrintLib + ConOut |
| `MdePkg.dec(32): MipiSysTLib not found` | 跳过子模块导致 include 路径缺失 | 子模块必须拉全 |
| `undefined reference to __stack_chk_fail` | Ubuntu 交叉编译器默认开栈保护 | 关栈保护 + 兜底实现 |
| `undefined reference to memcpy` | GCC LTO 把结构体拷贝变成 libc 调用 | 用 CopyMem/SetMem 实现 memcpy/memset |

## 真机踩过的坑（固件/启动部分）

| 现象 | 根因 | 修法 |
|---|---|---|
| 固件刷入但驱动无输出 | `[Depex] TRUE` 时定时器协议还没就绪，`SetTimer` 失败 | Depex 改为依赖 GOP |
| 屏幕变绿但无文字 | 那时 `GraphicsConsoleDxe` 还没接管帧缓冲 | 注册 `SimpleTextOut` 协议通知后再打印 |
| 画的图形是稀疏点阵 | 帧缓冲是**可缓存映射**，少量分散写没到显存 | 绘制后按缓存行回扫（步长 16 个 32 位字） |
| `ExitBootServices` 返回 Invalid Parameter | ① AArch64 的 runtime 粒度是 64KB，平台按 4KB 分配 ② `MapKey` 被收尾回调弄失效 | ① 把越界 runtime 区向外扩到 64KB 边界 ② 重试取新 key |
| GOP 的 `PixelsPerScanLine` 不可信 | 实测报 1000，真实 1080 | 用 `FrameBufferSize/4/H` 反推 |
| 驱动入口读到的 `FrameBufferBase` 是 0 | 读取时机太早 | 绘制前重新读一次 GOP |
| 固件里找不到设备树 | 这版固件不把 DT 放进 EFI 配置表 | 把真机导出的 DT 编进驱动 |
