# 进度与恢复指南（2026-10-18）

## 一句话现状

小米 13 (fuxi) 上跑着**我们自己编的 UEFI 固件**，它启动后会加载**我们自己写的引导器**，
引导器退出 Boot Services、构造 `boot_args`、跳转到**我们自己编的内核**，内核在屏幕上输出信息。

## 已经验证通过的（全部真机验证）

| 编号 | 能力 | 关键证据 |
|---|---|---|
| M1 | 自编 UEFI 运行我们的代码 | 屏幕变色、打印 `EL1` |
| M2 | 退出 Boot Services | `ExitBootServices` 返回成功，退出后仍能写显存 |
| M3 | 裸机自绘文字 | 黑底白字显示 `M3/EL1/PITCH/FB/FDT` |
| M4 | 内核交接 | `x0=DTB`，读到 `D00DFEED` |
| M5 | 独立内核运行 | 屏幕显示 `KERNEL RUNNING` |
| G2 | boot_args 结构一致 | `REV=2`、`PHYSBASE=0x80000000`、`DTLEN≈0xC7D3F` |

## 进行中 / 未完成

| 编号 | 内容 | 卡在哪 |
|---|---|---|
| M6 | 自建 XNU 编译 | **进行中**：源码编译全过，链接卡 `__start`（start.s 未参与汇编） |
| G3 | 把 XNU 的早期输出接到帧缓冲 | 方案已定（内存环形缓冲），未实现 |
| G4 | XNU 推进到设备初始化 | 硬障碍：缺 Apple 私有驱动 + kernelcache 加密 |

## 关键结论（省得以后重走弯路）

1. **AArch64 上 `RUNTIME_PAGE_ALLOCATION_GRANULARITY` 是 64KB**，高通平台按 4KB 分配
   runtime 区 → `ExitBootServices` 必然失败。修法：把越界 runtime 区**向外扩到 64KB 边界**。
2. **`GetMemoryMap` 与 `ExitBootServices` 之间不能有任何分配**，连打印一行日志都会让 key 失效。
3. **GOP 的 `PixelsPerScanLine` 不可信**（实测报 1000，真实 1080）；用 `FrameBufferSize/4/H` 反推。
4. **帧缓冲是可缓存映射**：少量分散写不会到显存，画完要按缓存行回扫（步长 16 个 32 位字）。
5. `FrameBufferBase` 在驱动入口时还是 0，要等到 BDS 阶段再读。
6. **固件不把设备树放进 EFI 配置表** → 我们把真机导出的 DT 编进了驱动。
7. XNU 的 `boot_args` 结构（xnu-8792）见 `docs/m6-xnu-plan.md`；两侧结构必须逐字节一致。

## 如何恢复

```
git clone https://github.com/Xyvern08371/ios-on-fuxi.git
cd ios-on-fuxi

# 改代码后
git push                    # 触发 CI 编固件
# 下载 fuxi-uefi-<编号>.zip，双击 scripts\flash_latest.bat 刷入

# 回到原厂系统
scripts\restore_pe.bat
```

CI 产物里 `version.txt` 会写清：提交号、run 号、固件补丁是否打上、镜像大小。

## 下次可以选的方向

| 方向 | 说明 | 难度 |
|---|---|---|
| **Linux 内核启动** | Linux 原生支持设备树与高通平台，驱动都在内核里 | 中，可完成 |
| 自己的内核继续长 | 加 GIC 中断、定时器、串口输出 | 低，循序渐进 |
| XNU | 已暂停；需要 Apple 私有驱动，缺件 | 极高，可能不可达 |

## 已知小问题（暂不处理）

- 屏幕上 `boot_args.CommandLine` 显示为 `-v` 之外的空缺：字体缺小写字形导致。
  已补 29 个字形，但**这一类显示细节先不追**，优先推进 XNU 编译关（G1）。
