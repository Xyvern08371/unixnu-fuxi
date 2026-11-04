// SPDX-License-Identifier: BSD-2-Clause-Patent
// fuxi（小米 13，SM8550）触控控制器的板级事实。每个常量都注明来源。
// 写法参照 UniXNU-sheng 的 package/TouchBoard.h，但内容是 fuxi 的实测/DT 数据，代码为本工程新写。
// 本文件不访问硬件，只给出常量和纯函数。
//
// 来源缩写：
//   DT    = 官方 OS3.0.309 vendor_boot DTB[2]（Kalama v2）+ dtbo[4]（8550 fuxi）经 fdtoverlay 合并后的设备树
//           （见 ../dtb/fuxi_merged.dts，路径 /soc/qcom,qupv3_1_geni_se@ac0000/spi@a90000/fts@0）
//   KAL   = LineageOS android_kernel_xiaomi_sm8550 drivers/pinctrl/qcom/pinctrl-kalama.c（REG_BASE 0x100000）
//   SHENG = UniXNU-sheng package/TouchBoard.h（同 SoC 的已验证值）
//   DEV   = 本机运行时实测（../../device_dump：spi0.0 绑定 fts、input "fts" 坐标 0..10799 x 0..23999）
#ifndef FUXI_TOUCH_BOARD_H
#define FUXI_TOUCH_BOARD_H
#include <stdint.h>

// ---- QUP / 串行引擎 ----
#define FTB_QUP_WRAPPER_BASE 0x00ac0000ULL   // DT: qcom,qupv3_1_geni_se@ac0000 reg <0xac0000 0x2000>；与 SHENG 相同
#define FTB_SE_BASE 0x00a90000ULL            // DT: spi@a90000 reg <0xa90000 0x4000>；与 SHENG 相同
#define FTB_SE_SIZE 0x4000ULL
#define FTB_QUP_SMMU_SID 0xa3                // DT: wrapper iommus = <&apps_smmu 0xa3 0>；与 SHENG 相同
#define FTB_SE_GIC_SPI 357                   // DT: spi@a90000 interrupts = <GIC_SPI 0x165 IRQ_TYPE_LEVEL_HIGH>
// 时钟：DT clocks = <&gcc 0x65>（se-clk），即 gcc_qupv3_wrap1_s4_clk；投票位、halt 寄存器与 SHENG 的 TB_VOTE_* 相同（同一 SE）

// ---- SPI 参数 ----
#define FTB_SPI_MODE 0                        // DT: fts@0 无 spi-cpol/spi-cpha
#define FTB_SPI_HZ 12000000u                  // DT: fts@0 spi-max-frequency = <12000000>（SHENG 的 Novatek 是 19.2 MHz）
#define FTB_SPI_CS_DELAY_US 10                // 驱动 ftsHardware.h SPI_DELAY_CS：拉高 CS 前等待 10 µs
#define FTB_SPI_4WIRE 1                       // 驱动 ftsHardware.h SPI4_WIRE

// ---- TLMM（GPIO n 的控制寄存器 = 0x0F100000 + 0x1000*n）----
#define FTB_TLMM_GPIO_BASE 0x0f100000ULL      // KAL: DT 节点基址 0xf000000 + REG_BASE 0x100000；与 SHENG 的 TB_TLMM_BASE 相同
#define FTB_GPIO_STRIDE 0x1000
#define FTB_GPIO_SPI_MISO 44                  // DT: qupv3_se4_spi_miso_active gpio44, function qup1_se4_l0, 6 mA, pull-down
#define FTB_GPIO_SPI_MOSI 45                  // DT: gpio45, qup1_se4_l1, 6 mA, pull-down
#define FTB_GPIO_SPI_CLK 46                   // DT: gpio46, qup1_se4_l2, 6 mA, pull-down
#define FTB_GPIO_SPI_CS 47                    // DT: mi_ts_cs_active gpio47, qup1_se4_l3, 6 mA, **pull-up**
#define FTB_GPIO_IRQ 25                       // DT: fts,irq-gpio = <&tlmm 25 0x2008>，低电平触发；mi_ts_active: gpio, 8 mA, pull-up
#define FTB_GPIO_RESET 24                     // DT: fts,reset-gpio = <&tlmm 24 0>，输出；mi_ts_active: gpio, 8 mA, pull-up
#define FTB_TLMM_SUMMARY_GIC_SPI 208          // DT: pinctrl@f000000 interrupts = <GIC_SPI 0xd0 LEVEL_HIGH>（TLMM 汇总中断，SHENG 用 32+208）
#define FTB_GPIO_IRQ_PDC_PIN 57               // Linux pinctrl-sm8550.c sm8550_pdc_map {25, 57}
#define FTB_GPIO_IRQ_PDC_GIC_SPI 537          // DT qcom,pdc-ranges 换算：PDC pin 57 -> GIC SPI 537（走 PDC 唤醒路径时用）
#define FTB_TLMM_INTR_STATUS_OFF 0xc          // KAL: intr_status_reg = REG_BASE + 0xc + 0x1000*n，bit0 = 中断挂起

static inline uint64_t ftb_tlmm_ctl(unsigned gpio) {return FTB_TLMM_GPIO_BASE + (uint64_t)gpio * FTB_GPIO_STRIDE;}
static inline uint64_t ftb_tlmm_io(unsigned gpio) {return ftb_tlmm_ctl(gpio) + 4;}
static inline uint64_t ftb_tlmm_intr_status(unsigned gpio) {return ftb_tlmm_ctl(gpio) + FTB_TLMM_INTR_STATUS_OFF;}

// ---- 电源（RPMh 管理）----
// 安卓实测（root，2026-10-31，../power/）：两路都**只有触控一个消费者**（spi0.0-vdd / spi0.0-avdd），
// 驱动加载后常开，息屏（Dozing）也不关；DT 里没有 regulator-boot-on / always-on。
// 结论：内核默认它们开机时是关的，只有触控驱动会打开 → XNU 接管时按“关着”处理，先投票再访问芯片
// （重复投票无害）。SHENG 的 TouchProbe 不操作电源，fuxi 需要补这一步。
#define FTB_VDD_RPMH_RESOURCE "ldob12"        // DT: vdd-supply -> rpmh-regulator-ldob12 / regulator-pm-humu-l12（PM8550 LDO12，pmic5_nldo515）
#define FTB_VDD_RPMH_ADDR 0x40900u            // 实测 /sys/kernel/debug/cmd-db：0x40900: ldob12
#define FTB_VDD_MV 1800u                      // DT: min = max = init = 1.8 V；实测 1800 mV，模式 fast(HPM)
#define FTB_AVDD_RPMH_RESOURCE "ldom6"        // DT: avdd-supply -> rpmh-regulator-ldom6 / regulator-pm8010m-l6（PM8010 LDO6，pmic5_pldo502ln）
#define FTB_AVDD_RPMH_ADDR 0x41b00u           // 实测 cmd-db：0x41b00: ldom6
#define FTB_AVDD_MV 3200u                     // DT: init 3.2 V（允许 1.8–3.2 V）；实测 3200 mV
// VRM 资源内的寄存器偏移与取值（Linux drivers/regulator/qcom-rpmh-regulator.c）
#define FTB_VRM_REG_VOLTAGE 0x0               // 单位 mV
#define FTB_VRM_REG_ENABLE 0x4                // 1 = 使能
#define FTB_VRM_REG_MODE 0x8                  // PMIC5 LDO：3 retention / 4 LPM / 7 HPM
#define FTB_VRM_MODE_HPM 7
#define FTB_POWER_SETTLE_MS 3                 // 驱动 fts_probe：fts_enable_reg 之后 mdelay(3) 再配 GPIO、复位
// 上电顺序：先 vdd 再 avdd（驱动 fts_enable_reg）；下电相反。按 ACTIVE_ONLY 投票、等待完成后再继续：
struct ftb_rpmh_cmd {uint32_t addr, data;};
static const struct ftb_rpmh_cmd ftb_power_on_cmds[] = {
    {FTB_VDD_RPMH_ADDR + FTB_VRM_REG_VOLTAGE, FTB_VDD_MV},
    {FTB_VDD_RPMH_ADDR + FTB_VRM_REG_MODE, FTB_VRM_MODE_HPM},
    {FTB_VDD_RPMH_ADDR + FTB_VRM_REG_ENABLE, 1},
    {FTB_AVDD_RPMH_ADDR + FTB_VRM_REG_VOLTAGE, FTB_AVDD_MV},
    {FTB_AVDD_RPMH_ADDR + FTB_VRM_REG_ENABLE, 1},
};

// ---- 坐标与屏下指纹 ----
#define FTB_X_MAX 10800                       // DT: fts,x-max；DEV: ABS_MT_POSITION_X max 10799
#define FTB_Y_MAX 24000                       // DT: fts,y-max；DEV: ABS_MT_POSITION_Y max 23999
#define FTB_SCALE 10                          // 屏幕 1080x2400，触控坐标是 10 倍（DT fts,support-super-resolution = <1>）
#define FTB_FOD_X 4420                        // DT: fts,fod-lx；/10 = 442，与 persist.vendor.sys.fp.fod.location.X_Y=442,2052 一致
#define FTB_FOD_Y 20520                       // DT: fts,fod-ly
#define FTB_FOD_SIZE 1960                     // DT: fts,fod-x-size = fts,fod-y-size；/10 = 196，与 fod.size 196 一致

static inline int ftb_to_pixel_x(int x) {return x / FTB_SCALE;}
static inline int ftb_to_pixel_y(int y) {return y / FTB_SCALE;}

// ---- 芯片 ----
#define FTB_CHIP_ID0 0x36                     // 驱动 ftsHardware.h（SALIXP 分支）；固件 st_fts_m3.ftb 头部 target = 0x4036
#define FTB_CHIP_ID1 0x40
#define FTB_FW_FILE "st_fts_m3.ftb"           // DT: fts,default-fw-name；/odm/firmware/st_fts_m3.ftb（139728 字节，fw_id 0x6335，fw_ver 0x53）
#define FTB_FW_RUNNING "53.42"                // 实测 /proc/tp_fw_version：芯片里跑的就是这份文件（fw 0x53 / cfg 0x42），无需刷写
#define FTB_LOCKDOWN "H820M31"                // 实测 /proc/tp_lockdown_info 48 38 32 30 4D 33 31（第 2 字节 0x38 = tp-vendor）
#define FTB_TP_VENDOR 0x38                    // DT: fts,cfg_0 fts,tp-vendor = <0x38>
#endif
