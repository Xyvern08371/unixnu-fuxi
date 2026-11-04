# fuxi 引导必需设备清单

由 `tools/inventory.py` 从 `fuxi_merged.dtb` 自动生成，**不要手改**。
数据来源：PixelOS_fuxi-17.0-20260929 的 vendor_boot + dtbo（已合并）。

## 关键参数

| 项 | 值 |
|---|---|
| PSCI | `/soc/psci, method=smc` |
| stdout-path | `-` |
| bootargs | `console=ttyMSM0,115200n8 kpti=0 kernel.panic_on_rcu_stall=1 service_lo` |
| 定时器节点 | `/soc/timer` |
| 保留内存区 | `66 项` |

## P1 — 没有它连第一行日志都打不出来

| 类别 | 节点 | compatible | reg | 中断 | status |
|---|---|---|---|---|---|
| CPU 拓扑 | `/soc/cpu-pmu` | `arm,armv8-pmuv3` | `-` | yes | okay |
| PSCI 电源管理 | `/soc/psci` | `arm,psci-1.0` | `-` | - | okay |
| 中断控制器 | `/soc/interrupt-controller@17100000` | `arm,gic-v3` | `0x17100000` | yes | okay |
| 中断控制器 | `/soc/interrupt-controller@17100000/msi-controller@17140000` | `arm,gic-v3-its` | `0x17140000` | - | okay |
| 系统定时器 | `/soc/timer` | `arm,armv8-timer` | `-` | yes | okay |
| 调试串口 | `/soc/qcom,qupv3_1_geni_se@ac0000/qcom,qup_uart@a9c000` | `qcom,geni-debug-uart` | `0xa9c000` | yes | ok |

## P2 — 早期启动必需

| 类别 | 节点 | compatible | reg | 中断 | status |
|---|---|---|---|---|---|
| PMIC / SPMI | `/soc/qcom,spmi@c42d000` | `qcom,spmi-pmic-arb` | `0xc42d000` | - | okay |
| PMIC / SPMI | `/soc/qcom,spmi@c42d000/qcom,pm8550@1` | `qcom,spmi-pmic` | `0x100000000 + 0x0` | - | okay |
| PMIC / SPMI | `/soc/qcom,spmi@c42d000/qcom,pm8550@1/pinctrl@8800` | `qcom,pm8550-gpio` | `0x8800` | - | okay |
| PMIC / SPMI | `/soc/qcom,spmi@c42d000/qcom,pm8550@1/pm8550-temp-alarm@a00` | `qcom,spmi-temp-alarm` | `0xa00` | yes | okay |
| PMIC / SPMI | `/soc/qcom,spmi@c42d000/qcom,pm8550b@7` | `qcom,spmi-pmic` | `0x700000000 + 0x0` | - | okay |
| PMIC / SPMI | `/soc/qcom,spmi@c42d000/qcom,pm8550b@7/pinctrl@8800` | `qcom,pm8550b-gpio` | `0x8800` | - | okay |
| PMIC / SPMI | `/soc/qcom,spmi@c42d000/qcom,pm8550b@7/pm8550b-temp-alarm-lite@c00` | `qcom,spmi-temp-alarm` | `0xc00` | yes | okay |
| PMIC / SPMI | `/soc/qcom,spmi@c42d000/qcom,pm8550b@7/pm8550b-temp-alarm@a00` | `qcom,spmi-temp-alarm` | `0xa00` | yes | okay |
| PMIC / SPMI | `/soc/qcom,spmi@c42d000/qcom,pm8550ve_f@5` | `qcom,spmi-pmic` | `0x500000000 + 0x0` | - | okay |
| PMIC / SPMI | `/soc/qcom,spmi@c42d000/qcom,pm8550ve_f@5/pinctrl@8800` | `qcom,pm8550ve-gpio` | `0x8800` | - | okay |
| … | 另有 107 项（PMIC / SPMI、RPMh / 通信、UFS 存储、引脚控制、时钟控制） | | | | |

## P3 — 能看见、能交互

| 类别 | 节点 | compatible | reg | 中断 | status |
|---|---|---|---|---|---|
| DSI / 面板 | `/soc/display_panel_vci` | `regulator-fixed` | `-` | - | okay |
| DSI / 面板 | `/soc/display_panel_vddd` | `regulator-fixed` | `-` | - | okay |
| DSI / 面板 | `/soc/display_panel_vddio` | `regulator-fixed` | `-` | - | okay |
| DSI / 面板 | `/soc/dsi_panel_pwr_supply` | `-` | `-` | - | okay |
| DSI / 面板 | `/soc/dsi_panel_pwr_supply/qcom,panel-supply-entry@0` | `-` | `0x0` | - | okay |
| DSI / 面板 | `/soc/dsi_panel_pwr_supply/qcom,panel-supply-entry@1` | `-` | `0x1` | - | okay |
| DSI / 面板 | `/soc/dsi_panel_pwr_supply/qcom,panel-supply-entry@2` | `-` | `0x2` | - | okay |
| DSI / 面板 | `/soc/dsi_panel_pwr_supply_M3` | `-` | `-` | - | okay |
| DSI / 面板 | `/soc/dsi_panel_pwr_supply_M3/qcom,panel-supply-entry@0` | `-` | `0x0` | - | okay |
| DSI / 面板 | `/soc/dsi_panel_pwr_supply_M3/qcom,panel-supply-entry@1` | `-` | `0x1` | - | okay |
| … | 另有 266 项（DSI / 面板、I2C / SPI、USB、显示 MDP、触摸） | | | | |

## P4 — 以后再说

| 类别 | 节点 | compatible | reg | 中断 | status |
|---|---|---|---|---|---|
| GPU | `/soc/kgsl-smmu@3da0000` | `qcom,qsmmu-v500` | `0x3da0000` | yes | okay |
| GPU | `/soc/qcom,kgsl-3d0@3d00000` | `qcom,adreno-gpu-gen7-2-0` | `0x3d00000` | yes | ok |
| GPU | `/soc/qcom,kgsl-iommu@3da0000` | `qcom,kgsl-smmu-v2` | `0x3da0000` | - | okay |
| GPU | `/soc/qcom,kgsl-iommu@3da0000/gfx3d_lpac` | `qcom,smmu-kgsl-cb` | `-` | - | okay |
| GPU | `/soc/qcom,kgsl-iommu@3da0000/gfx3d_secure` | `qcom,smmu-kgsl-cb` | `-` | - | okay |
| GPU | `/soc/qcom,kgsl-iommu@3da0000/gfx3d_user` | `qcom,smmu-kgsl-cb` | `-` | - | okay |
| NPU / 其它 | `/soc/adsp-sleepmon` | `qcom,adsp-sleepmon` | `-` | - | okay |
| NPU / 其它 | `/soc/qcom,cvp@ab00000/qcom,msm-cvp,mem_cdsp` | `qcom,msm-cvp,mem-cdsp` | `-` | - | okay |
| NPU / 其它 | `/soc/qcom,dma-heaps/qcom,adsp` | `-` | `-` | - | okay |
| NPU / 其它 | `/soc/qcom,dma-heaps/qcom,secure_cdsp` | `-` | `-` | - | okay |
| … | 另有 124 项（NPU / 其它、Wi-Fi / 蓝牙、摄像头、音频） | | | | |

## 统计

- 归类到清单的节点：**533**
- 其中 status != okay（需要先打开）：**34**

  - `/soc/spf_core_platform/cdc_dmic01_pinctrl` (disabled)
  - `/soc/spf_core_platform/cdc_dmic23_pinctrl` (disabled)
  - `/soc/spf_core_platform/cdc_dmic45_pinctrl` (disabled)
  - `/soc/spf_core_platform/cdc_dmic67_pinctrl` (disabled)
  - `/soc/spf_core_platform/fm_i2s1_pinctrl` (disabled)
  - `/soc/spf_core_platform/wsa2_swr_clk_data_pinctrl` (disabled)
  - `/soc/spf_core_platform/wsa_swr_clk_data_pinctrl` (disabled)
  - `/soc/wsa_spkr_en1_pinctrl` (disabled)
  - `/soc/wsa_spkr_en2_pinctrl` (disabled)
  - `/soc/qcom,dsi-display-secondary` (disabled)
  - `/soc/qcom,qupv3_1_geni_se@ac0000/i2c@a84000` (disabled)
  - `/soc/qcom,qupv3_1_geni_se@ac0000/i2c@a88000` (disabled)
  - `/soc/qcom,qupv3_1_geni_se@ac0000/i2c@a8c000` (disabled)
  - `/soc/qcom,qupv3_1_geni_se@ac0000/i2c@a90000` (disabled)
  - `/soc/qcom,qupv3_1_geni_se@ac0000/i2c@a94000` (disabled)

> 用法：P1 全部打通之前，不要碰 P3 以后的东西。
> 每打通一项，就把它的状态从 ⬜ 改成 ✅（建议单独维护一张进度表）。
