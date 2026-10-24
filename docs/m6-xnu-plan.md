# M6：XNU 引导（研究性，结果不保证）

## 为什么单独写一份

这一段和 M1–M5 性质不同：M1–M5 每一步都是"做了就能成"，M6 是**研究性工程**，
存在无法靠工程手段绕过的障碍。这份文档把阶段、判据、以及已知硬障碍写清楚。

## 分四个关口

| 关口 | 内容 | 判据 | 风险 |
|---|---|---|---|
| **G1 编译** | 在 Linux CI 上用 cctools-port(ld64/as) 交叉编译开源 XNU（arm64） | 产出 `kernel.elf`/镜像 + 日志无致命错误 | 高：XNU 的构建系统假设 macOS 环境 |
| **G2 交接** | loader 构造 `boot_args`，`x0 = &boot_args`，跳到 XNU 入口 | 我方内核能按同一结构读出字段（已做自测） | 中：结构版本必须与编译的 XNU 完全一致 |
| **G3 输出** | 把 XNU 的早期输出接到帧缓冲 | 屏幕上出现 XNU 自己的字符串或 panic | 中高：需改 pexpert 的 console 路径 |
| **G4 平台** | 让 XNU 能推进到设备初始化之后 | 可重复的、可解释的 panic 位置 | 极高：缺 Apple 私有驱动 |

## G2 已完成的部分（2026-10-18）

loader 里已实现：

```c
typedef struct { ... } BOOT_ARGS;     // 与 xnu-8792.81.2 pexpert/arm64/boot.h 同构
BuildBootArgs(dtb, dtbSize, memSize);
JumpToBootArgs(entry, (UINTN) &gBootArgs, stackTop);   // x0 = boot_args
```

自测内核按同一结构读取并显示 `REV / PHYSBASE / MEMSIZE / DTB / DTLEN / CMDLINE`，
用来证明"两侧对结构的理解一致"。

## G3 的具体做法（预期）

XNU 在 arm64 上没有 framebuffer 概念，早期输出走 `pexpert` 的串口/`pe_putc` 路径。
我们计划在 CI 里对 XNU 打一个**最小 patch**：

1. 在 `pexpert/arm64/` 里把底层单字符输出函数改成写帧缓冲（用 `boot_args.Video` 的字段）；
2. 或者提供一个"输出钩子"，让它把字符写进一个内存缓冲区，同时由我们的小内核轮询显示。

第二种更稳：**不要求 XNU 会画字，只要它把字符写进约定的内存环形缓冲**，
我们保留的显示循环负责渲染。这样补丁面积极小。

## G4 的硬障碍（如实记录）

- XNU 假定显示、电源、存储、USB 由 iBoot 侧提供，**高通版驱动不存在**
- 真机 kernelcache 加密且与设备绑定；本项目**不做解密或提取**
- 因此"iPhone 系统跑在小米手机上"不是时间问题，而是**缺少不存在的组件**

## 可行的替代目标

- 在 QEMU/模拟器里运行开源 XNU（不涉及真机固件）
- 把 fuxi 引导到 **Linux**（Linux 原生支持设备树与高通平台，属于可完成的工程）
