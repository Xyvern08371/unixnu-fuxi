// SPDX-License-Identifier: BSD-2-Clause-Patent
// fuxi（小米 13）主屏面板与显示控制器的板级事实。每个常量都注明来源。
// 来源：DT = 官方 OS3.0.309 vendor_boot DTB[2] + dtbo[4] 合并后的设备树（../dtb/fuxi_merged.dts），
//       面板节点 /soc/qcom,mdss_mdp@ae00000/qcom,mdss_dsi_m3_38_0c_0a_dsc_cmd；
//       UEFI = hanzi123-bilp/uefi-fuxi（MemoryMapLib "Display Reserved"、fuxi.dsc PcdFrameBuffer*）；
//       DEV  = 本机实测（SurfaceFlinger：1080x2400，60/90/120 Hz，HDR 420/0.323 nit）。
#ifndef FUXI_PANEL_BOARD_H
#define FUXI_PANEL_BOARD_H

// ---- 面板身份 ----
#define FPB_PANEL_NAME "xiaomi m3 38 0c 0a sec cmd mode dsc dsi panel"   // DT qcom,mdss-dsi-panel-name
#define FPB_PANEL_ID_HI 0x4d33       // DT mi,panel-id = <0x4d33 0x380c00>，0x4d33 = "M3"
#define FPB_PANEL_ID_LO 0x380c00
// DDIC：命令集是三星显示的惯例（F0 5A5A/A5A5 解锁、B0 全局偏移、F7 0F 更新），名字里的 sec 也对得上；具体型号未核实

// ---- 分辨率 / 物理尺寸 ----
#define FPB_WIDTH 1080               // DT qcom,mdss-dsi-panel-width = <0x438>
#define FPB_HEIGHT 2400              // DT qcom,mdss-dsi-panel-height = <0x960>
#define FPB_WIDTH_UM 66300           // DT qcom,mdss-pan-physical-width-dimension = <0x297>（0.1 mm）
#define FPB_HEIGHT_UM 147300         // DT ...-height-dimension = <0x5c1>；对角线 6.36"

// ---- 链路 ----
#define FPB_DSI_LANES 4              // DT lane-0..3-state，lane_map_0123
#define FPB_DSI_CMD_MODE 1           // DT qcom,mdss-dsi-panel-type = "dsi_cmd_mode"，burst，TE 引脚同步
#define FPB_DSI_CLOCK_HZ 1100000000u // DT qcom,mdss-dsi-panel-clockrate = <0x4190ab00>
#define FPB_BPP 24                   // DT qcom,mdss-dsi-bpp = <0x18>，rgb_swap_rgb
// 三套 timing（DT timing@0/1/2）：60 / 120 / 90 Hz；h 前后沿 124/124、h 同步 32；v 前沿 128、后沿 132、同步 24
#define FPB_H_FP 124
#define FPB_H_BP 124
#define FPB_H_PW 32
#define FPB_V_FP 128
#define FPB_V_BP 132
#define FPB_V_PW 24

// ---- DSC ----
#define FPB_DSC_BPP 8                // DT qcom,mdss-dsc-bit-per-pixel
#define FPB_DSC_BPC 8
#define FPB_DSC_SLICE_W 540          // DT 0x21c
#define FPB_DSC_SLICE_H 40           // DT 0x28
#define FPB_DSC_SLICE_PER_PKT 2
// 注意：on-command 第 0 条（9E，90 字节 PPS）里的 pic_height = 0x09D8 = 2520，与 timing/2B 页地址的 2400 不一致，待核实

// ---- 显示控制器地址 ----
#define FPB_MDSS_MDP_BASE 0x0ae00000ULL      // DT qcom,mdss_mdp@ae00000 reg mdp_phys 0x84000；GIC SPI 83
#define FPB_DSI0_CTRL_BASE 0x0ae94000ULL     // DT qcom,mdss_dsi_ctrl0@ae94000（dsi-ctrl-hw-v2.7）
#define FPB_DSI0_PHY_BASE 0x0ae95000ULL      // DT qcom,mdss_dsi_phy0 dsi_phy（v5.2）
#define FPB_DSI0_PLL_BASE 0x0ae95500ULL      // DT pll_base
#define FPB_DISP_CC_BASE 0x0af0f000ULL       // DT dsi_ctrl0 disp_cc_base（4 字节窗口）
#define FPB_MDP_INTF_BASE 0x0ae36000ULL      // DT dsi_ctrl0 mdp_intf_base

// ---- UEFI/ABL 留下的帧缓冲（第一阶段直接用它出图）----
#define FPB_SPLASH_BASE 0xb8000000ULL        // DT /reserved-memory/splash_region；UEFI "Display Reserved"；与 sheng 完全相同
#define FPB_SPLASH_SIZE 0x02b00000ULL
#define FPB_FB_BPP 32                        // UEFI PcdFrameBufferColorDepth
#define FPB_FB_STRIDE_PIXELS 1080            // UEFI PcdFrameBufferWidth（注释要求与 ABL 扫描 stride 一致）
#define FPB_DEMURA_BASE 0xa2a80000ULL        // UEFI "Display Demura" 0x2B00000（保留，勿占用）

// ---- GPIO（TLMM，控制寄存器 0x0F100000 + 0x1000*n）----
#define FPB_GPIO_RESET 133           // DT qcom,platform-reset-gpio；复位序列 <0 1 1 10>：低 1 ms → 高 10 ms
#define FPB_GPIO_TE 86               // DT qcom,platform-te-gpio，function mdp_vsync，te-pin-select 1
#define FPB_GPIO_ESD 49              // DT mi,esd-err-irq-gpio，低电平
#define FPB_GPIO_VDDIO_EN 126        // DT display_panel_vddio：1.8 V，GPIO126 高有效
#define FPB_GPIO_VDDD_EN 42          // DT display_panel_vddd：1.5 V，GPIO42 高有效
#define FPB_GPIO_VCI_EN 127          // DT display_panel_vci：3.0 V，GPIO127 高有效
// 上电顺序（panel-supply-entry@0/1/2）：vddio（等 2 ms）→ vddd → vci（等 10 ms）→ 复位 → on-command

// ---- 亮度 ----
#define FPB_BL_MIN 4                 // DT qcom,mdss-dsi-bl-min-level
#define FPB_BL_MAX 4095              // DT qcom,mdss-dsi-bl-max-level = <0xfff>（12 bit）
#define FPB_BL_INIT 307              // DT qcom,mdss-brightness-init-level = <0x133>
#define FPB_BL_DCS 0x51              // DT bl_ctrl_dcs；qcom,mdss-dsi-bl-inverted-dbv => 51 的两个字节按大端发送（按驱动逻辑推断）
#define FPB_DC_THRESHOLD 450         // DT mi,mdss-dsi-panel-dc-threshold = <0x1c2>
#endif
