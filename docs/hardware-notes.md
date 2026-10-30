# fuxi 硬件实测数据

来源：`PixelOS_fuxi-17.0-20260929` 的 `vendor_boot.img` + `dtbo.img`
（用户提供，提取于 2026-10-17）。**全部是真机固件里的原始数据，不是推测。**

提取方式：

```bash
python tools/bootimg.py info    vendor_boot.img
python tools/bootimg.py extract vendor_boot.img -o rom/out/vb
python tools/bootimg.py extract dtbo.img        -o rom/out/dtbo
```

## SoC 与内存

| 项 | 值 | 来源 |
|---|---|---|
| SoC | `qcom,kalama`（SM8550） | base DT `model` |
| msm-id | `0x207` / `0x218`（+平台位） | fuxi overlay |
| board-id | `0x10008` | fuxi overlay |
| DRAM 基址 | **`0x80000000`** | `/reserved-memory` 最低区 `gunyah_hyp_region@80000000` |
| 低 4G 末端 | `0x1_0000_0000` | `llcc_lpi_region@ff800000 + 0x600000 = 0xffe00000` |
| `/memory` 节点 | `reg = <0 0 0 0>`（占位） | ABL 运行时才填 |

> `/memory` 是空的这件事很重要：**别指望从 DT 里直接读内存大小**，它由 bootloader 在启动时打补丁。

## 中断与调试串口

| 项 | 地址 | compatible |
|---|---|---|
| GICv3 distributor | `0x17100000`，0x10000 | `arm,gic-v3` |
| GICv3 redistributor | `0x17180000`，0x200000 | 同上 |
| PDC（唤醒中断） | `0x0b220000`，0x30000 | `qcom,kalama-pdc` |
| **调试 UART** | **`0x00a9c000`，0x4000** | `qcom,geni-debug-uart` |
| 高速串口 | `0x00a90000`，0x4000 | `qcom,msm-geni-serial-hs` |
| 另一路串口 | `0x00898000`，0x4000 | `qcom,msm-geni-serial-hs` |

bootloader 给的 cmdline 里写着 `console=ttyMSM0,115200n8`，`ttyMSM0` 就是 `0xa9c000` 这一路。

**这解决了一个大问题**：早期日志有地方打了，不用盲调。

## CPU 与显示

- CPU：**8 核**，`cpu@0/100/200/300/400/500/600/700`（4×A510 + 3×A715 + 1×X3）
- 显示控制器：`qcom,mdss_mdp@ae00000`（`qcom,sde-kms`），size 0x84000
- PMIC：`pm8550` / `pm8550b` / `pm8550ve_f` / `pm8550vs` / `pmk8550` / `pmr735d`（都是 overlay 里加的）

## dtbo 里有什么

`dtbo.img` 是 **12 个 overlay**，不是 12 棵完整设备树：

| # | 内容 | 是否本机 |
|---|---|---|
| 0–7 | crow / kalama 各种 ATP/IDP/QRD/RUMI 参考板 | 否 |
| 8 | fuxi (msm-id 0x258/0x259) | 疑似 |
| 9 | fuxi (msm-id 0x25c) | 疑似 |
| **10** | **fuxi (msm-id 0x207/0x218, board-id 0x10008)** | **是** |
| **11** | **fuxi (同上，另一个平台位)** | **是** |

`vendor_boot` 里则是 5 棵完整 DT：3 棵 `qcom,crow`、2 棵 `qcom,kalama`。

**结论：fuxi 的实际设备树 = kalama base DT + fuxi overlay 合并后的结果。**
所以 M3 的任务不是"抄一棵树"，而是：

1. 实现 FDT overlay 合并（`fragment@N` + `target` phandle + `__fixups__` / `__local_fixups__` 解析）
2. 合并 `vb_dtb_04.dtb` + `dtbo_10_id0_rev0.dtb`
3. 得到真正跑在手机上的那棵树，再和 iPhone X 的参考 DT 做字段对照

## 对 profile 的修正

`appledt/profiles/fuxi.json` 已按实测更新：

| 字段 | 之前（猜） | 现在（实测） |
|---|---|---|
| DRAM 基址 | `0x80000000` | `0x80000000` ✅ 猜对了 |
| UART | `0x990000` ❌ | **`0xa9c000`** |
| CPU 核数 | 2 ❌ | **8** |
| GIC | 没有 | **`0x17100000` / `0x17180000`** |

## 合并后的完整设备树

```bash
python tools/overlay.py rom/out/vb/vb_dtb_04.dtb rom/out/dtbo/dtbo_10_id0_rev0.dtb \
       -o rom/out/fuxi_merged.dtb
```

实测结果：

```
重编号 phandle 529 个, 本地引用 345 处, 外部符号 439 处
fragment 应用 77 个, 跳过 0 个
写出 fuxi_merged.dtb (4852 节点, 696993 字节)
校验: 通过（无重复 phandle, 无残留 0xffffffff 占位符）
```

合并后能看到 fuxi 特有的东西：`/soc/xiaomi-touch`、`/soc/display_panel_vci|vddio|vddd`、
68 个 pm8550 相关节点、cirrus / nfc 的 pinctrl 组。

## 运行时实测（adb + su，2026-10-17）

`/sys/firmware/fdt`（817,983 字节）直接从手机 dump 出来，存于 `rom/device/fuxi_runtime.dtb`。

**合并树 vs 运行时树：差 8 个节点（多）和 1 个节点（少）。**
多出来的只有 `/hypervisor/*`（Gunyah 虚拟机监控器，运行时才挂上去）、`/memory/ebuff`、
两个 GPU 频率档位和 `__symbols__`。说明 `dtbo_10` 就是本机用的那份 overlay，
overlay 合并的实现是对的。

### 真实内存布局（`/memory` 有 9 段，不是一整块）

| 起始 | 大小 |
|---|---|
| `0x80000000` | `0x00e00000` |
| `0x811d0000` | `0x56e30000` |
| `0xd8140000` | `0x00020000` |
| `0xd8800000` | `0x0`（占位） |
| `0xe7cb0000` | `0x18350000` |
| `0x880000000` | `0x39d00000` |
| `0x8c0000000` | `0xc0000000` |
| `0x980000000` | `0x180000000` |
| `0x8b9f00000` | `0x01e00000` |

`MemTotal = 11,457,728 kB`（≈ 10.9 GiB，12 GB 机型）。
**做移植时不能假设内存连续**，必须按这张表逐段处理。

### 其它运行时信息

| 项 | 值 |
|---|---|
| root model | `Qualcomm Technologies, Inc. 8550 fuxi` |
| 槽位 | `_a` |
| 面板（cmdline） | `msm_drm.dsi_display0=qcom,mdss_dsi_m3_38_0c_0a_dsc_cmd` |
| 分区 | A/B 全双份；另有 `uefi_a` / `uefi_b`，内容是 **ELF**（64 位容器） |
| root 方案 | KernelSU（`context=u:r:ksu:s0`），`adb shell su` 可用 |
| pstore | 空（当前无崩溃记录） |

## 还没拿到的

- `init_boot.img`：PixelOS 的 ramdisk 在这个分区里（`boot.img` 的 ramdisk 长度为 0）
- 面板的具体节点：DT 里只有 `display_panel_*` 供电 regulator，面板本体由内核模块/固件加载
- `uefi_a` 到底是什么：头部是 ELF，需要进一步解析才知道是不是 Qualcomm 的 UEFI 环境

## 真机实测：我们的代码在 fuxi 上运行（2026-10-18）

用自己的 DXE 探针（`loader/Probe.c`，编进固件、无需任何输入）在真机上取得的实测结果：

| 项 | 值 | 意义 |
|---|---|---|
| **CurrentEL** | **EL1** | 跳内核**不需要** EL2→EL1 降级，省掉 HCR_EL2/eret 那段 |
| GOP | 可用 | 能直接写帧缓冲，不需要依赖文字输出 |
| 显示 | 1080x2400 | 与 fuxi.dsc 里 PcdMipiFrameBuffer 一致 |

过程记录（每一步都是实测确认，不是推断）：

1. 自编 UEFI 能启动、点亮屏幕、进菜单、进 Shell
2. `[Depex] TRUE` 的驱动会被 DXE 调度执行（入口 `wfi` 使手机卡住）
3. 早期 `SetTimer` 必然失败 → 定时器方案全部无效
4. Depex 改成 `gEfiGraphicsOutputProtocolGuid` 后: GOP 可用、帧缓冲可写（整屏变色成功）
5. 刷屏时刻 `GraphicsConsoleDxe` 尚未接管 → 无文字；注册 `gEfiSimpleTextOutProtocolGuid` 通知后才打印成功

**结论：在 fuxi 上，"加载我们的代码 → 拿到帧缓冲 → 输出信息"这条链已经完全打通。**
## M2 实测：离开 Boot Services 之后仍在运行（2026-10-18）

探针 v10 的流程与实测结果：

| 步骤 | 现象 | 结论 |
|---|---|---|
| 1. 写帧缓冲刷绿 + 控制台打印 | 绿屏 + `EL1 FDT=...` | Boot Services 阶段一切正常 |
| 2. 忙等约 3 秒 | 画面保持 | — |
| 3. `ExitBootServices` | 未死机 | 内存图获取与退出成功 |
| 4. 跳 payload，直接写显存刷蓝 | **整屏变蓝** | **在无任何 UEFI 服务的裸机环境下执行成功** |

这一步的意义：内核启动时所处的环境（无 Boot Services、只有物理内存）已经被我们亲手验证过一遍。
后面接内核时，"跳过去就死" 这类问题已经排除了大半。