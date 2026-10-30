# ios-on-fuxi

在小米 13（`fuxi` / SM8550）上尝试引导 **自建 XNU** 的个人项目。

定位：**从头自己搭一遍**——自己编 UEFI 固件、自己写引导器、自己编内核。
复用社区已有的 fuxi 平台底座（edk2-msm / Renegade）的源码，但固件是我们自己构建的。

## 现在的状态（2026-10-18）

**小米 13 上正在跑我们自己编的固件 + 我们自己的内核。**

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M0 | 工具链与骨架 | ✅ |
| M0.5 | 固件解析 + 真机设备树（4852 节点） | ✅ |
| M1 | 真机运行我们的代码（`CurrentEL=EL1`、GOP、帧缓冲） | ✅ |
| M2 | `ExitBootServices` 成功（进入真正的裸机环境） | ✅ |
| M3 | 裸机自绘文字（自带点阵字体，不依赖 UEFI 控制台） | ✅ |
| M4 | 内核交接（关中断 / 换栈 / `x0`=设备树 / 读到 `D00DFEED`） | ✅ |
| M5 | 独立内核运行（屏幕上显示 `KERNEL RUNNING`） | ✅ |
| M6 | 自建 XNU 能编译并链接 | ✅ 16.4MB Mach-O |
| M7 | XNU 在真机上产生可见输出 | 🟡 加载器全链路打通，内核执行到 `_start`，卡在开 MMU |
| M8 | XNU 平台层移植（显示/中断/存储） | ⬜ |

详细状态、架构改动和踩坑记录见 [`docs/status.md`](docs/status.md)。

细节与踩坑记录见 [`docs/roadmap.md`](docs/roadmap.md)。

## 实测得到的关键数据（真机）

| 项 | 值 |
|---|---|
| CurrentEL | **EL1**（跳内核不需要 EL2 降级） |
| 帧缓冲 | `0xB0000000`，1080×2400，BGRX |
| 真实行跨距 | **1080**（GOP 报的 1000 是错的） |
| 设备树 | 固件不放进 EFI 配置表 → 已把真机导出的 818KB DT 编进驱动 |
| `boot_args` | 与 xnu-8792 `pexpert/arm64/boot.h` 逐字段一致 |

## 目录

```
ios-on-fuxi/
├─ appledt/                 设备树工具链（纯 Python，可跑可测）
│  ├─ apple_dt.py           FDT 读写引擎 + Apple 风格 DT 合成 + CLI
│  ├─ profiles/fuxi.json    目标设备树 profile
│  └─ selftest.py           11 项自测
├─ tools/                   工具集合（Python）
│  ├─ bootimg.py            boot / vendor_boot / dtbo 解析与抽取
│  ├─ overlay.py            FDT overlay 合并
│  ├─ inventory.py          设备树 -> 引导必需设备清单
│  ├─ macho.py              Mach-O 解析（规划 XNU 加载用）
│  ├─ gen_dtb_blob.py       设备树 -> C 数组（编进固件）
│  ├─ gen_blob.py           任意二进制 -> C 数组
│  ├─ patch_firmware.py     固件补丁（ExitBootServices 相关）
│  └─ selftest.py           10 项自测
├─ loader/                  注入固件的探针驱动
│  ├─ Probe.c               引导器主体（GOP/自绘字体/boot_args/跳转）
│  └─ Probe.inf
├─ payload/                 独立编译的最小内核（M5 用）
│  ├─ entry.S / kernel.c / link.ld
├─ xnu-stubs/               XNU 构建所需的替身（不碰 Apple 二进制）
│  ├─ os/firehose_buffer_private.h
│  └─ patch_files_arm64.py  放开 start.s 的编译条件
├─ scripts/                 刷机、恢复、macOS 本地构建
├─ .github/workflows/       build-fuxi-uefi（固件）/ build-xnu（XNU）
└─ docs/
   ├─ roadmap.md            里程碑、当前卡点、所有踩坑记录
   ├─ RESUME.md             中断后如何继续
   ├─ status-2026-10-18.md  当日成果
   ├─ m5-complete.md        独立内核运行
   ├─ m6-xnu-plan.md        XNU 路线与障碍
   ├─ boot-chain.md         引导链分析
   └─ hardware-notes.md     真机硬件实测
```

## 快速开始

```bash
cd appledt
python selftest.py                       # 11/11 通过
python apple_dt.py synth profiles/fuxi.json -o fuxi.dtb
python apple_dt.py dump fuxi.dtb
```

刷机（Windows）：

```
scripts\flash_latest.bat       # 自动找最新的 fuxi-uefi-*.zip 刷入
scripts\restore_pe.bat         # 恢复原厂 boot 分区
```

## 边界

本仓库只做**自己写的代码**：自己构建的固件、引导器、设备树工具、自建内核。

**不做**：解密/分发苹果加密二进制、绕过激活锁、提供刷机包。

XNU 部分只用 `apple-oss-distributions/xnu` 的开源源码自行编译，
不加载、不修改任何 Apple 预编译内核。

## 下一步（按顺序）

1. 让 `osfmk/arm64/start.s` 参与汇编 → 链接出 `kernel.release`（M6 收尾）
2. 写 Mach-O 加载器：分段映射 → 关 MMU → `x0=boot_args` → 跳 `__start`（M7）
3. 看 XNU 死在哪一步，逐个补平台层（M8，未知领域）
