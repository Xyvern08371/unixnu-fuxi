# 小米 13（fuxi）触控与面板驱动资料（面向 UniXNU 移植）

> 整理时间：2026-10-31。所有数据都来自官方固件、设备树、真机实测或开源驱动，每一项都注明出处。只是没有经过 UniXNU 上机验证。
> 配套文件：`drivers/FuxiFtsTouch/`（触控驱动，第 7 节）、`package/FuxiTouchProbe.cpp`（内核探针）、`package/Fuxi*Board.h`（板级常量，已通过主机测试）、`facts/`（机器可读事实与 73 组面板命令序列）、`dtb/`（合并后的完整设备树）、`firmware/`（触控固件）、`dts/fuxi.dts`（UniXNU 设备树草稿）。

## 0. 结论

| 项目 | 与 Pad 6S Pro（sheng，UniXNU 已跑通）的关系 | 工作量 |
|---|---|---|
| 触控 SPI 控制器、时钟、引脚、中断 | **完全相同**：SPI4 @0xa90000，wrapper 0xac0000，SID 0xa3，GPIO44-47，中断 GPIO25（TLMM 汇总中断 SPI 208） | 直接复用 `QcomGeniSpi`、`TouchBoard.h` 里的时钟和引脚代码 |
| 触控芯片 | **不同**：fuxi 是 ST FingerTip（FTM5，芯片 ID 36 40），sheng 是 Novatek | 要写新的协议层（第 2 节的协议已经整理完整） |
| 触控固件 | **更简单**：FTS 芯片自带 flash，开机不用像 Novatek 那样由主机下载固件 | — |
| 触控电源 | **已实测（第 6 节）**：两路只供触控，安卓里由触控驱动打开后常开；按"XNU 接管时是关的"处理。RPMh 地址已确定：vdd `ldob12` = 0x40900，avdd `ldom6` = 0x41b00 | 加 5 条 RPMh 投票（`FuxiTouchBoard.h` 的 `ftb_power_on_cmds`），之后等 3 ms |
| 第一阶段出图 | **相同**：splash 帧缓冲 0xB8000000 / 0x2B00000，1080x2400x32bpp | 走 `GopFramebuffer` 路线，不用写 DSI 驱动 |
| 原生显示驱动 | 三星 DDIC + DSC 命令模式；命令序列、时序、电源时序都已解码 | 第二阶段才需要 |

## 1. 数据来源与可信度
1. **设备树**：官方 OS3.0.309 线刷包（md5 已校验）里 vendor_boot 的 DTB[2]（"Kalama v2 SoC"，对应本机 `ro.boot.dtb_idx=2`、soc_id 519 rev 2.0），加 dtbo[4]（"8550 fuxi"，msm-id 0x207）。用 `fdtoverlay` 合并，得到与 ABL 启动时一致的完整设备树（`dtb/fuxi_merged.dtb`），所有 phandle 都已解析（`tools/dt_facts.py`）。
2. **触控驱动**：LineageOS `android_kernel_xiaomi_sm8550` 里的 `drivers/input/touchscreen/fts_spi`（GPL，最近一次提交 2025-01-23）。compatible `"st,spi"`、模块名 `fts_touch_spi`、描述 "STMicroelectronics MultiTouch IC Driver" 三项都与 fuxi 的 DT 和 TWRP ramdisk 里的模块一致，可以确认是 fuxi 实际在用的小米版驱动。
   - Qualcomm 的参考驱动 `touch-drivers/st`（compatible `"st,fts"`）**不是**这个，不要拿错。
   - 源码放在 `ref_src/fts_spi/`，仅供查阅。UniXNU 是 BSD-2-Clause-Patent 许可，**不要把 GPL 代码直接贴进去**，按本文的事实重新实现。
3. **引脚和中断换算**：Linux `pinctrl-sm8550.c`（GPIO→PDC 映射）、LineageOS 下游 `pinctrl-kalama.c`（`REG_BASE 0x100000`），以及 DT 中的 `qcom,pdc-ranges`。
4. **交叉印证**：
   - 本机实测：`spi0.0` 绑定 fts，触控坐标范围 0..10799 × 0..23999，屏下指纹位置属性 `442,2052`、大小 196；
   - SurfaceFlinger 上报的 HDR 420 / 0.323 nit 与 DT 一致；
   - 社区 fuxi UEFI 移植（hanzi123-bilp/uefi-fuxi）里的显示保留区和帧缓冲参数与 DT 一致。

## 2. 触控（ST FTS，`/soc/qcom,qupv3_1_geni_se@ac0000/spi@a90000/fts@0`）

### 2.1 硬件连接（详见 `package/FuxiTouchBoard.h`）
| 项 | 值 | 与 sheng |
|---|---|---|
| 总线 | QUP1 SE4 SPI，SE 0xa90000（0x4000），wrapper 0xac0000，SE 中断 GIC SPI 357，SMMU SID 0xa3，时钟 `gcc_qupv3_wrap1_s4_clk` | 相同 |
| SPI | mode 0，**12 MHz**，4 线，拉高 CS 前等 10 µs | 频率不同（sheng 19.2 MHz） |
| 引脚 | MISO 44 / MOSI 45 / CLK 46 / CS 47，function `qup1_se4_l0..l3`，6 mA；CS 上拉，其余下拉 | 相同 |
| 中断 | GPIO25，低电平，上拉 8 mA；TLMM 汇总中断 GIC SPI 208（sheng 用 `32+208`）；走 PDC 唤醒时是 PDC pin 57 → GIC SPI 537 | 相同 |
| 复位 | GPIO24，输出，上拉 8 mA | — |
| 电源 | vdd = RPMh `ldob12`（pm_humu_l12）1.8 V；avdd = RPMh `ldom6`（**pm8010m_l6**，相机 PMIC）3.2 V。上电先 vdd 后 avdd | sheng 不操作电源 |
| TLMM 地址 | GPIO n 控制寄存器 = 0x0F100000 + 0x1000·n，+0x4 IO，+0xC 中断状态（bit0） | 相同 |
| 坐标 | 0..10800 × 0..24000（屏幕的 10 倍，`support-super-resolution`） | — |
| 屏下指纹区 | 中心 (4420, 20520)，边长 1960 | — |

### 2.2 SPI 帧格式
- **写**：一次传输，`[操作码][地址，大端][数据]`。硬件寄存器的地址是 4 字节。
- **读**：**同一次片选**内先发 `[操作码][地址]`，再收 `1 + n` 字节，**第 1 个字节是 dummy，丢掉**。
- 单次读写最多 1024 字节（READ_CHUNK / WRITE_CHUNK）。

| 操作码 | 含义 |
|---|---|
| `FA` / `FB` | 写 / 读硬件寄存器（SPI 形态；I2C 形态下读也是 FA） |
| `A6` / `A7` | 写 / 读 framebuffer |
| `A8` / `A9` | 写 / 读配置内存 |
| `87` | 读事件 FIFO（无地址） |
| `A0 mode settings` | 设置扫描模式 |
| `A2` / `A4` | 设置特性 / 系统命令 |

| 硬件寄存器 | 地址 | 说明 |
|---|---|---|
| 芯片 ID | 0x20000000 | 读 2 字节 = `36 40`（固件 `st_fts_m3.ftb` 头部 target 也是 0x4036） |
| 固件版本 | 0x20000004 | |
| 系统复位 | 0x20000024 | 写 0x81（没有复位脚时才用） |
| IER | 0x20000029 | 0x41 = 使能中断（驱动定义了，但 fuxi 的流程里没有直接写） |
| ICR | 0x2000002D | bit1 = 4 线 SPI（复位后收不到 ready 时设置） |
| CRC 状态 | 0x20000078 | 低 2 位非 0 表示 flash CRC 错误 |

### 2.3 启动流程（与驱动的 `fts_probe` → `fts_init` → `fts_init_sensing` 一致）
1. 配置引脚（2.1），确认 vdd 1.8 V、avdd 3.2 V 已上电（不确定就先投票打开，见 2.6）。
2. **复位**：GPIO24 拉低，等 10 ms，拉高。
3. **等待就绪**：每 2 ms 读一次 FIFO（`87` → 1 + 8 字节），直到某个事件的第 0 字节是 `0x03`（CONTROLLER_READY），超时 100 ms。复位加等待最多重试 3 次。
4. **收不到 ready**：写 ICR（0x2000002D）的 bit1 切到 4 线 SPI，等 1 ms，然后每隔 10 ms 读一次芯片 ID，最多 3 次，应为 `36 40`。读到说明芯片在，但 flash 可能没有固件。
5. （可选）读 System Info（framebuffer 里的系统信息区），拿固件版本和配置 ID。
6. **开始扫描**：`A0 00 00` → 等 50 ms → `A0 00 01`；唤醒或恢复路径用 `A0 00 FF`。
7. 开中断（GPIO25 低电平）。

### 2.4 中断与事件
- 中断到来时，先读 1 个事件（`87` → 1 + 8 字节）。**第 7 字节低 5 位**是 FIFO 里剩下的事件数 N（最多 31），N 大于 0 时再一次性读 `8·N` 字节。每个事件按第 0 字节分派。
- 触摸事件（`0x13` 按下 / `0x23` 移动 / `0x33` 抬起）的解码，fuxi 用的是超分辨率格式：
  - `type = ev[1] & 0x0F`（1 手指、2 手套、3 触控笔、4 手掌、5 悬停）
  - `id = ev[1] >> 4`（0–9）
  - `x = ev[3] << 8 | ev[2]`，`y = ev[5] << 8 | ev[4]`；**除以 10** 就是屏幕像素
  - `major = ((ev[0] & 0x0C) << 2) | (ev[6] >> 4)`，`minor = ((ev[7] & 0xC0) >> 2) | (ev[6] & 0x0F)`
- 其它事件：`0x43` 状态（`ev[1]=0x01` 是命令回显），`0x53` 用户事件（手势、接近等），`0xF3` 错误（`ev[1]`：0x06 看门狗，0x20–0x23 / 0xA0–0xA6 是 CRC 错误，0xF0 是 ESD）。
- **按第 0 字节的高 4 位分派**（驱动 `eventId = data[0] >> 4`）：第 0 字节的 bit2–3 还带着接触面积 major 的高位，所以 0x13、0x17、0x1B、0x1F 都是按下事件。只认整字节 0x13 会漏事件（早期版本的头文件就犯了这个错误，已改正）。
- 现成实现：`drivers/FuxiFtsTouch/FtsTouchCore.c`（`fts_decode_point`、`fts_touch_apply`），测试在 `drivers/FuxiFtsTouch/Test/`。

### 2.5 固件
- `/odm/firmware/st_fts_m3.ftb`：139728 字节，头部 `55 AA 55 AA`，ftb v1，target 0x4036，fw_id 0x6335，fw_ver 0x53，cfg_ver 0x42。已从官方 odm 取出，放在 `firmware/`；产线测试阈值是 `stm_fts_production_limits.csv`。
- 芯片自带 flash，**正常开机不需要下载固件**。安卓驱动开了 `FW_UPDATE_ON_PROBE`，只在文件版本更新时才写 flash。UniXNU 前期**不要实现写 flash**，以免把触控刷坏。

### 2.6 风险与待实测项
1. **电源**（已实测，见第 6 节）：两路都只供触控，DT 里没有 boot-on/always-on，安卓里由触控驱动打开。所以 XNU 接管时**应按关着处理**：访问芯片前，先向 RPMh 投 `ftb_power_on_cmds` 里的 5 条命令，等 3 ms，再配 GPIO、复位。即使电源其实已经开着，重复投票也无害。sheng 包里的 `QcomRpmh.c` 可以拿来发命令。
2. 坐标轴方向：DT 没有 x/y 翻转属性，驱动默认不翻转，以实机为准。
3. DT 里有 21 个小米私有调参属性（边缘抑制、点击灵敏度、跟手性等），LineageOS 驱动没有解析，基础触控不需要。
4. 备选料 GT9916（I2C 0x5d）的节点在这份 DT 里是 `disabled`，这台机器用的是 FTS（`tp-vendor = 0x38`）。如果遇到 GT9916 的机器，需要另做适配。

## 3. 面板（三星 DDIC，`qcom,mdss_dsi_m3_38_0c_0a_dsc_cmd`；详见 `package/FuxiPanelBoard.h`）

### 3.1 基本参数
| 项 | 值 |
|---|---|
| 面板 ID | `mi,panel-id = <0x4d33 0x380c00>`（"M3"） |
| DDIC | 命令集是三星显示的惯例：`F0 5A 5A` / `F0 A5 A5` Level-2 解锁/上锁，`B0` 全局参数偏移，`F7 0F` 更新。加上面板名里的 "sec"，判断为**三星显示**（具体型号未核实） |
| 分辨率 / 尺寸 | 1080×2400，66.3×147.3 mm（6.36"） |
| 链路 | DSI0 单路，4 lane，**命令模式**，TE 引脚同步，burst，1.1 GHz，RGB888 |
| DSC | 8 bpp / 8 bpc，切片 540×40，每包 2 切片，block prediction 打开 |
| 时序 | 3 套：60 / 120 / 90 Hz。h 前后沿 124/124、同步 32；v 前沿 128、后沿 132、同步 24 |
| 亮度 | DCS `0x51`，12 bit（4–4095，开机初值 307）。`bl-inverted-dbv`，两个字节按大端发送（按驱动逻辑推断）。DC 调光阈值 450 |
| HDR | 峰值 420 nit，黑电平 0.323 nit（与本机 HWC 上报一致） |

### 3.2 控制器与 GPIO
- MDSS/MDP 0xae00000（GIC SPI 83），DSI0 控制器 0xae94000（v2.7），DSI0 PHY 0xae95000、PLL 0xae95500（v5.2），DISP_CC 0xaf0f000，MDP INTF 0xae36000。
- GPIO：复位 133（低 1 ms → 高 10 ms），TE 86（function `mdp_vsync`），ESD 中断 49（低电平）。
- 电源上电顺序：vddio 1.8 V（GPIO126 使能，之后等 2 ms）→ vddd 1.5 V（GPIO42）→ vci 3.0 V（GPIO127，之后等 10 ms）→ 复位 → on-command。

### 3.3 第一阶段：沿用 UEFI 留下的帧缓冲
- splash 区 **0xB8000000 / 0x2B00000，与 sheng 完全相同**，UEFI 移植的 "Display Reserved" 也是这个值。格式 1080×2400，32 bpp，stride 1080 像素（uefi-fuxi 的 `PcdFrameBufferWidth`）。所以 `board.toml` 里 `bootimg.dtb_node` 的 splash_region 可以照抄 sheng。
- 另有 Demura 保留区 0xA2A80000（0x2B00000），不要占用。
- 这个阶段不需要碰 DSI，画面由 ABL/UEFI 点亮的面板持续扫描输出。命令模式面板需要有人触发刷新，这一点要看 UniXNU `GopFramebuffer` 在 sheng 上怎么处理（sheng 的面板是视频模式还是命令模式，**未核实**）。

### 3.4 第二阶段：原生 DSI 驱动需要的数据（`facts/`）
- 73 组命令序列已逐条解码成 `facts/panel_cmds_*.txt`。主要的几组：
  - `on-command`（63 条）：先发 PPS（`9E`，90 字节）→ `9D 01` → `11` 退出睡眠，等 120 ms → `35` 开 TE → `2A`/`2B` 设 1080×2400 窗口 → 一系列三星私有寄存器 → `29` 开显示；
  - `off-command`（9 条）：`28` 关显示，等 20 ms → … → `10` 进入睡眠，等 120 ms；
  - `timing-switch`（8 条，切换刷新率）；`nolp`；HBM、FOD-HBM、local-HBM（屏下指纹点亮）、DOZE（息屏）、flat-mode、dimming。
- **待核实**：on-command 里的 PPS 写的 `pic_height = 0x09D8 = 2520`，与 timing 和 `2B` 页地址的 2400 不一致。要么面板忽略这个值，要么驱动另外发了一份 PPS。写原生驱动前需要对照 Qualcomm 显示驱动源码或实机确认。

## 4. 建议的验证顺序
1. 用 CI 构建的启动镜像（解密和核对见 README 的"上机"一节），通过 `fastboot boot` 临时启动，确认能进 UniXNU 菜单。只是临时启动，不写分区。
2. 打通 GENI SPI，读芯片 ID `36 40`。读不到就先查电源（2.6 第 1 条）。
3. 复位，等 `0x03`，然后 `A0 00 01`，接中断，验证事件解码。可以先在屏幕上打点，看坐标是否除以 10 后与屏幕对齐。
4. 出图走 splash 帧缓冲。原生 DSI 驱动放到最后。

## 5. 安卓侧还能补采的数据（需要 root）
- ~~触控和面板电源的实时状态~~：已完成，见第 6 节。
- 面板实际收到的命令：开启 `msm_drm` 的 DSI 调试日志后抓 `dmesg`，可以用来核对 PPS 的高度问题。
- 开机时电源何时打开：手机已连续运行 4 天，开机日志已被覆盖；下次重启后马上抓 `dmesg`，可以看到触控驱动的上电时间点。

## 6. 安卓侧实测记录（root，2026-10-31，原始数据在 `power/`）
| 项目 | 结果 | 结论 |
|---|---|---|
| 触控 vdd `pm_humu_l12` | 已开，1800 mV，模式 fast；**唯一消费者 `spi0.0-vdd`** | 只有触控用 |
| 触控 avdd `pm8010m_l6` | 已开，3200 mV；**唯一消费者 `spi0.0-avdd`** | 相机并不用它，只有触控用 |
| 息屏（Dozing）时的触控电源 | 两路都保持开（use 1） | 驱动加载后常开（屏下指纹、双击唤醒需要） |
| 面板 vci / vddio / vddd | 亮屏 3000 / 1800 / 1500 mV；**息屏全部关闭**（use 0） | 面板每次亮屏都会重新走一遍上电时序 |
| RPMh 资源地址（`/sys/kernel/debug/cmd-db`） | `ldob12` = **0x40900**，`ldom6` = **0x41b00** | 写进 `FuxiTouchBoard.h` 的投票表 |
| VRM 寄存器（Linux `qcom-rpmh-regulator.c`） | +0x0 电压（mV），+0x4 使能，+0x8 模式（PMIC5 LDO HPM = 7） | 同上 |
| 芯片里运行的固件 | `/proc/tp_fw_version` = **53.42** | 与 `st_fts_m3.ftb` 头部（fw 0x53 / cfg 0x42）一致，不需要刷写 |
| 锁定信息 | `48 38 32 30 4D 33 31` = **"H820M31"** | 第 2 字节 0x38 = DT 的 `tp-vendor` |
| 真实触摸事件（dmesg） | `Event 0x13 - Press ID[0] type = 1`、`Event 0x33 - release` | 印证了第 2.4 节的事件 ID 和类型编码 |
| 驱动上电后的等待 | `fts_probe`：`fts_enable_reg` 之后 `mdelay(3)` 再配 GPIO | 投票后等 3 ms |

**仍然无法在安卓下确认的**：XNU 接管那一刻电源的真实状态。RPMh 汇总了多个主控的投票，Linux 只能看到自己这一份，而且开机日志已经被覆盖。现在的做法（总是先投票）不依赖这个答案。2026-11-02 上机对比（`p4-power0`）：不投票时控制器不应答，说明至少在那次启动里，两路电源在 XNU 接管时不可用。

## 7. 触控驱动与 CI（2026-10-31）

### 7.1 结构（与 sheng 的 Novatek 驱动同样分层）
| 文件 | 作用 |
|---|---|
| `drivers/FuxiFtsTouch/FtsProtocol.c` | 通过 `struct fts_bus`（全双工收发、延时、复位脚三个回调）访问芯片：寄存器读写、读芯片 ID、读 FIFO（先读 1 个事件，再按它报告的剩余数一次读完）、复位并等待就绪（3 次重试，失败后按驱动的做法切 4 线 SPI 并读 ID，区分"没固件"和"没芯片"）、开始扫描 |
| `drivers/FuxiFtsTouch/FtsTouchCore.c` | 事件到触点：每个触点 ID（0–9）占一个槽位。手指、手套、手掌、触控笔算按下；悬停算抬起；坐标截断到 x/y 最大值。看门狗、ESD 错误，以及没有请求过的就绪事件，都会置 `reset_needed`。另有板级坐标映射（交换、镜像、缩放） |
| `package/FuxiTouchProbe.cpp` | 内核探针。时钟、引脚、DMA、SMMU 的代码沿用 sheng 的 `TouchProbe.cpp`（总线相同），芯片相关部分换成 FTS：RPMh 上电、复位脚、低电平中断加 FIFO。导出的 `native_touch_*` 符号与 sheng 版一致，sheng 的 HID 层（`ShengHidInput`）可以直接读 |

`drivers/FuxiFtsTouch` 是子模块，指向独立的组件仓库 [OddlyLabs/FuxiFtsTouch](https://github.com/OddlyLabs/FuxiFtsTouch)。

### 7.2 探针的启动参数
| 参数 | 默认 | 说明 |
|---|---|---|
| `fuxi-touch=1..4` | 关 | 1 快照（含在 cmd-db 里按名字查 `ldob12`、`ldom6`）；2 RPMh 投票上电，等 3 ms，打开 QUP 时钟，配引脚（数据线和时钟下拉、CS 上拉、复位脚输出高、中断脚上拉）；3 GENI SPI 12 MHz，复位，等 `0x03`，读 ID `36 40`；4 `A0 00 00` → 50 ms → `A0 00 01`，接中断，读事件，发布触点 |
| `fuxi-touch-power=0` | 1 | 跳过 RPMh 投票。2026-11-02 实测：跳过后控制器不应答，所以只用于对比 |
| `fuxi-touch-tcs` | 2 | apps RSC DRV2 的活动 TCS（DT `qcom,tcs-config`：TCS 0–2 是活动 TCS） |
| `fuxi-touch-hz` | 12000000 | SPI 速率（不超过 DT 的 12 MHz） |
| `fuxi-touch-poll=1` | 0 | 不用中断，每 8 ms 读一次 FIFO |
| `fuxi-touch-map` | 0 | 发布前的坐标变换：1 交换 x/y，2 镜像 x，4 镜像 y（坐标轴方向要上机确认，见 2.6） |
| `fuxi-touch-panic` | 0 | 1：请求的阶段结束或失败时 panic，panic 信息就是 4 行诊断，可以在 panic 屏上读结果（现在还没有显示驱动）；2：在阶段 4 里，第一次完整的按下、抬起之后也 panic |
| `fuxi-touch-hid=1` | 0 | 开始扫描后启动 `ShengHidInput` 的触控数字化器（`FuxiHidProbe.cpp`），把每组触点作为 HID 报告送出（第 4 行的 `hid` 计数）。panic 信息多一行 `HID`。为了让报告里的触摸确实经过 HID，要等 HID 启动结束（设备和事件驱动起来、某一步失败，或者过了 20 秒）之后的第一次抬起才出报告，太早点的那一下要再点一次 |

- **启动入口**：`bsd_init` 在 `IOKitInitializeTime()` 之后、`vfsinit()` 之前调用 `native_touch_probe()`（`patches/xnu/fuxi-touch-probe.patch`）。探针在自己的内核线程里运行；没有 `fuxi-touch` 参数时立即返回。每个阶段的 4 行结果也会打印到内核日志。

- **中断**：TLMM 检测下降沿，经汇总中断 SPI 208 唤醒线程。线程一直读 FIFO，直到中断线变回高电平，所以读的过程中来的新事件不会丢。另外每 100 ms 检查一次线电平，防止漏掉边沿。
- **坐标**：`ShengHidInput` 把 x 按 0..30480、y 按 0..20320 换算到 HID 的逻辑范围，所以探针把 fuxi 的 0..10800 × 0..24000 线性映射到这两个范围再发布。最终 HID 坐标和屏幕成正比。
- **诊断页**：`native_touch_rows[0..3]` 以 "FTS" 开头，依次显示：
  - 阶段和时钟；
  - 引脚寄存器；
  - 电源（cmd-db 查到的地址、TCS 返回码）、芯片 ID、复位结果、最后一个事件；
  - 事件计数、触点和中断计数。
- **多核状态**（2026-11-02）：启动参数里有 `sheng-smp=1` 时，panic 信息在这 4 行之后再加两行 `SMP`（`smpText`），数据来自 ArmCpu 记录的变量。
  - 第一行：已运行的副核数 `run`、PSCI 调用方式 `c`（1 smc，2 hvc）、启动核的 MPIDR `b`、出报告时所在的核 `cpu`、调度器可用的处理器数 `av`。然后是核 1–7 各自的步骤 `st`（1 nub 启动，2 注册，3 启动线程在跑，4 已发 PSCI CPU_ON，5 新核进入 initCPU，6 GIC redistributor 就绪，7 运行）、失败码 `f` 和 CPU_ON 返回值 `psci`，最后是 IPI 的发出数和收到数。
  - 第二行：每个核收到的定时器中断 `tmr` 和 IPI `ipi`。
  - 没有 `sheng-smp` 时没有这两行，报告和以前一样。

### 7.3 尚未验证（需要上机）
1. RPMh：TCS 的完成位不开中断时会不会置位不确定，所以等不到时只记录 `w-1`，不算失败。TCS 2 在 fuxi 的 UEFI 下是否空闲也没确认，`fuxi-touch-tcs` 可以换成别的 TCS。2026-11-02 上机：请求返回 0，完成位没等到（`w-1`），芯片随后正常应答。2026-11-02 用 `fuxi-touch-power=0` 对比过：不投票时复位后收不到就绪事件，芯片 ID 读成 `00 00`，所以投票是必需的。那次是从 panic 屏手动按键进的 fastboot。
2. GENI 不提供"拉高 CS 前等 10 µs"的设置（驱动的 `SPI_DELAY_CS`）。12 MHz 下应该问题不大，但没有实测。2026-11-02 上机：复位、读 FIFO、读芯片 ID 的传输全部成功（`xf0`）。
3. 坐标轴方向、`ShengHidInput` 在 fuxi 竖屏下的方向处理。2026-11-02 上机：请机主在左下方点了三次，读到 `2885,18595`、`1295,16685`、`1635,19935`，都落在左下方，说明坐标轴没有交换、没有镜像；还不算校准。HID 层已接入（2026-11-02，设备仓库见 `package/FuxiHidProbe.cpp`），还没上机验证。
4. 启动时机：探针在 `bsd_init` 里启动，这时 IOKit 已经可用。2026-11-02 已验证：探针在自己的内核线程里跑完第 3 阶段，panic 屏正常显示 4 行报告。

### 7.4 CI
见 README 的"CI"一节。

**第一阶段**（提交 `920093c`，2026-11-01）：借用 sheng 的构建。先跑 sheng 配置的 XNU 构建拿到编译记录，再按 sheng 编译触控探针的参数（`-Wall -Wextra -Werror` 加几项例外）编译本项目的探针和驱动，最后检查符号解析。结果：
- sheng 原版探针（对照）、`FuxiTouchProbe.cpp`、`FtsProtocol.c`、`FtsTouchCore.c`、`GeniSpi.c`、`QcomRpmh.c` 全部编译通过；
- 本项目目标文件引用 39 个强符号，全部能在 1011 个 XNU 目标文件（`.o` 和 `.cpo`）里找到，没有与 XNU 重复定义的符号；
- 唯一的弱引用 `armcpu_spi_attach` 在同一次构建出来的 `build/armcpu/libArmCpu.a` 里。

**第二阶段**（2026-11-01 起）：本仓库改成 UniXNU 官方模板（`examples/device`）结构的 fuxi 设备仓库，CI 直接编译 fuxi 自己的内核。见第 8 节。

## 8. 设备仓库结构（2026-11-01）

按 UniXNU 的"Port a device"流程，以官方根项目为基础，社区的 fuxi 移植只作参考：

| 仓库 | 作用 |
|---|---|
| [OddlyLabs/UniXNU](https://github.com/OddlyLabs/UniXNU)（fork 自 UniXNU/UniXNU，分支 `fuxi`） | 构建工具和组件目录。`components.toml` 加了组件 `FuxiFtsTouch`（依赖 `QcomGeniSpi`），并有中英文文档页；`bootimg` 加了 fuxi 需要的两个选项 |
| [OddlyLabs/uefi-fuxi](https://github.com/OddlyLabs/uefi-fuxi)（fork 自 UniXNU/uefi-sheng，分支 `fuxi`） | 板级 UEFI 固件：官方 sheng 固件，加上 matejkoo217/uefi-fuxi 的 9 个 fuxi 提交（保留原作者） |
| [OddlyLabs/FuxiFtsTouch](https://github.com/OddlyLabs/FuxiFtsTouch) | 组件仓库：FTM5 协议和触点跟踪，带主机测试 |
| 本仓库 | fuxi 设备仓库：`board.toml`、`feeds.toml`、`configs/fuxi_defconfig`、`dts/fuxi.dts`、`patches/xnu/`、`package/`、`scripts/build-fuxi-touch.py`、`porting.toml` |

- **内核配置**：实际生效的配置是 arch、SoC、OS 三个配置片段再加上设备的 defconfig。设备 defconfig 在模板基础上关掉了 Adreno（SoC 片段默认打开），并加上触控归档。归档按顺序构建：corecrypto（普通版和命名空间版）、ArmDTPlatform、ArmCpu、SoftwareAES 及其绑定、libpthread、mockfs 测试用文件系统（OS 片段打开了 `CONFIG_XNU_SOURCE_MOCKFS`）、`build-fuxi-touch.py`。
- **启动钩子补丁**：上下文只用 XNU 原有的行，所以上游改动它前后的共享补丁时，这个补丁不会失效。已确认它能在 arch、SoC、OS 三组补丁之后干净应用。CI 里链接出来的内核中，`bsd_init` 确实调用了 `native_touch_probe`。
- **porting.toml**：UniXNU 的 `scripts/porting-record.py check` 通过（13 个区域）。上游的检查器还不认识 `FuxiFtsTouch` 组件，所以本仓库的记录检查用 fork 里的检查器。
- **固件的选择**：UniXNU 自己提供启动菜单和 XNU 加载器（DarwinBoot），但它们是 UEFI 模块，手机上还要有板级 UEFI 固件。上游 Mu-Silicium 没有 fuxi；所有 fuxi 固件都是社区仓库，而且都派生自官方的 UniXNU/uefi-sheng。所以以官方 uefi-sheng 为基础，只移植 matejkoo217 的 fuxi 提交：这些提交改动小、说明清楚，结论都在真机上测量过，Kerfand 用同样的提交已经启动到 XNU。
- **启动镜像**：根据那几个提交里的真机测量结果：
  - fuxi 的 ABL 用 `fastboot boot` 临时启动时，拒绝 v4 镜像（"Invalid Parameter"），所以临时启动用 v0 容器；
  - 镜像头里写固件地址会被拒绝（"Load Error"），所以 shim 的加载偏移写 0，再由 shim 自己把固件卷复制到固件地址；
  - ABL 把启动镜像的 ramdisk 留在 vendor_boot 里，固件看不到，所以负载紧跟在固件卷后面放进内核镜像，头部偏移 `0x10` 的镜像大小也要把它算进去。

  这两项（加载偏移、负载放进内核镜像）做成了 fork 里 `unixnu bootimg` 的通用选项，在本地测试过；附加的设备树用固件仓库里的 FdtBlob，它带有 ABL 选择设备树时要匹配的 board-id。
- **交付**：镜像里有苹果 kernelcache 的内容，CI 只上传加密后的版本（AES-256 加 RSA-OAEP），私钥只在机主电脑上（`X:\Xiaomi13\keys\`，不在任何仓库里）。payload 用的平台种子是固定的测试值，以后启动到系统时再换成手机自己的值。
- **CI 结果**（2026-11-01，[run 41273003819](https://github.com/OddlyLabs/unixnu-fuxi/actions/runs/41273003819)，提交 `2bbd399`）：内核、payload、DEBUG 固件和启动镜像全部构建通过。
  - 第一次固件构建失败：fuxiPkg 的 `RAW.inc` 把三个厂商配置文件（`SecParti.cfg`、`uefipil.cfg`、`QcomChargerCfg.cfg`）放在了 `FUXI_VENDOR_HW` 开关外面，只用 Mu 驱动构建时会去找不存在的厂商文件。uefi-fuxi `87554bf9` 把它们放到对应驱动的开关下。
  - 启动镜像 11.1 MiB（v0）。本地解密后用 `ci/check-boot-image.py` 核对：shim 头里的加载偏移是 0；内核镜像大小 0x0C300200，与 Kerfand 实测能启动的值相同；固件卷就是 CI 构建的那份；payload 里有带触控探针的内核、ADT（chip-id 0x207）和启动参数 `fuxi-touch=3 fuxi-touch-panic=1`。
  - 固件这一步也能在 Linux 上单独构建（Ubuntu 26.04，clang 21），只改固件时不必等 macOS 的 CI。
- **第一次上机**（2026-11-02，用 `fastboot boot` 临时启动上面那个镜像）：
  - bootloader 接受了 v0 镜像（`Booting OKAY`）。屏幕上先是固件的 DEBUG 日志；UniXNU 菜单启动 DarwinBoot，DarwinBoot 画出绿色色条；入口探针接着画出蓝色（进入内核，MMU 还关着）和品红（即将打开 MMU）两条。
  - 之后既没有 XNU 的文字，也没有 panic 屏，手机一直没有出现在 USB 上。
  - 结论：固件、菜单、DarwinBoot 和镜像格式都没问题；内核停在打开 MMU 到 `PE_init_printf`（第一个能往屏幕上写字的位置）之间。
  - 下一步用会自动重启的入口探针定位（README 的“探针镜像”一节）。两个社区移植（mouse233、Kerfand）的内核在同一颗 SoC 上能越过这一段，内存窗口大小也和本仓库相同；它们都用 sheng 的 kit，本仓库用模板组件 ArmDTPlatform、ArmCpu，这是首先要排查的差异。
- **探针定位**（2026-11-02）：在 `arm_init` 的各个调用之后放会自动重启的探针，逐个上机。
  - 能走到：打开 MMU、进入 `arm_init`、`cpu_data_init`、`PE_init_platform`、`configure_misc_apple_regs`。
  - 走不到：`ml_parse_cpu_topology` 之后（以及更后面的 `processor_bootstrap`、`arm_vm_init`）。
  - 原因：`dts/fuxi.dts` 照 sheng 把 cpu0–2 标成 E 簇、cpu3–7 标成 P 簇，内核据此建立两个簇；但 BCM2837 配置的 `MAX_CPU_CLUSTERS` 仍是 1（sm8550-common 只把 `MAX_CPUS` 改成了 8），开发版内核里的断言 `cluster_id < MAX_CPU_CLUSTERS` 失败，在控制台出现之前就 panic 了，所以屏幕上什么都没有。
  - sheng 用它自己的设备补丁 `zzyf-sheng-amp.patch` 解决了这个问题（`MAX_CPU_CLUSTERS` 改成 2，并配好 E/P 两簇的调度）。fuxi 的核心布局完全相同，所以原样带上这个补丁。
  - 另外，读出了这台手机（12 GB）真实的内存布局：固件内存表来自一台 8 GB 手机，高端内存里有两段（`0x8B9D00000` 起 2 MiB、`0x8BBD00000` 起约 22 MiB）在这台手机上并不是安卓的内存，固件却当成了空闲内存。内核用的窗口不受影响，但固件需要修正。
- **第二个卡点**（2026-11-02，带 AMP 补丁的内核）：
  - 探针一路走到 `PE_create_console` 都会重启，但下一个调用 `PE_init_printf` 之后的探针没有重启（只测了一次）；正式镜像停在色条上，既没有内核文字，也没有 panic 屏。
  - 可疑点：模板和配置片段都没有打开 `CONFIG_XNU_DT_PANIC_REGION`。这时 BCM2837 目标会用树莓派的固定地址：`PE_create_console` 映射物理地址 `0x3C0FC000`，读一个字，再把 16 KiB 清零。在树莓派上那是内存；在这台手机上，`/proc/iomem` 和设备树里都没有任何内存或设备覆盖这个地址。sheng 和两个社区 fuxi 移植都打开了这个选项。
  - 这段代码在 `initialize_screen` 之前运行，这时内核还没有映射帧缓冲，所以在这里出错时 panic 屏画不出来，和看到的现象一致。但这还只是推断：这次访问到底会出错、卡住还是被忽略，并没有测量过，要等上机验证。
  - 今天有 3 次启动跑过这段代码（探针 `a2-console`、`b11-createcons` 和正式镜像）。前两次之后手机都正常回到了安卓；第三次是正式镜像，手机停在色条上，要强制重启。
  - 已打开这个选项，并在 CI 里加了检查：`PE_create_console` 再出现这个地址，构建就失败。
- **启动到 `bsd_init`，触控第 3 阶段通过**（2026-11-02，提交 `e901139`，镜像 SHA-256 `e360c41a…`）：
  - 打开这个选项后（内核只改了这一处），XNU 越过控制台初始化，一直跑到 `bsd_init`。触控探针在自己的内核线程里跑完第 3 阶段，然后按设计 panic，panic 屏显示 4 行报告。
  - 报告的逐项解读见 `evidence/2026-11-02-first-boot.md`，要点如下：
    - cmd-db 里按名字查到 `ldob12` = 0x40900、`ldom6` = 0x41b00，和安卓下实测一致；RPMh 请求返回 0（完成位没等到，见 7.3）。
    - QUP 时钟都在运行；GPIO44–47 读回 0x85、0x85、0x85、0x87，即功能 1、6 mA、数据线和时钟下拉、CS 上拉，和设备树完全一致；复位脚输出高电平。
    - GENI 是 QUP 3.9，SPI 时钟正好 12 MHz。
    - 第一次复位就收到 CONTROLLER_READY（`03 00 00`），读到芯片 ID `36 40`，所有 SPI 传输都没出错。
    - panic 时内核管理着 4.61 GiB 内存（窗口 4.75 GiB 减去内核和启动数据）。
  - 这是第一次由本项目自己的驱动在真机上和触控芯片通信。下一步是第 4 阶段：开始扫描、接中断、读触摸事件（`fuxi-touch=4 fuxi-touch-panic=2`，摸一下屏幕，第一次完整的按下、抬起之后 panic 报告坐标）。
- **第 4 阶段第一次尝试**（2026-11-02 12:03，镜像 `a4314587…`）：屏幕上不是触控报告，而是 `AMFI: No PMGR?`（`ConfigurationSettings.cpp:235`）。
  - AMFI 是苹果的代码签名组件（iPadOS 内核缓存里的 kext，原样预链接），它会等一个叫 `ApplePMGRNub` 的电源管理服务，等不到就 panic。第 3 阶段的探针在 `bsd_init` 之后不到一秒就主动 panic 了，所以之前没遇到；第 4 阶段要等人摸屏幕，AMFI 的检查就先到了。
  - AMFI 对它只做一件事：通过 nub 读一个值、或上第 2 位、再写回去；原厂实现读出来是 `0xffffffff`、写入什么都不做，不碰任何硬件。
  - 解决办法沿用 UniXNU-sheng：原样带上它的 PMGR 桥 `ShengPlatformPower.cpp`，打开 `CONFIG_XNU_SHENG_PMGR`，启动参数加 `sheng-pmgr=2`。sheng 的构建脚本要用本地旧构建留下的预链接内核做核对，CI 里没有，所以 `scripts/build-fuxi-platform-power.py` 只改了这一处，核对挪到链接之后，由 `ci/check-pmgr-bridge.py` 对实际发出的内核做（同时核对 AMFI 和 PMGR 的指令约定）。
  - 这个桥不是电源管理：它的所有电源操作都会 panic 并报出编号。
- **带 PMGR 桥上机，第 4 阶段通过**（2026-11-02，提交 `484a650`，记录见 `evidence/2026-11-02-first-boot.md`）：
  - 只开桥、不跑探针（`p1-pmgr`）：AMFI 放行，内核走到找系统分区，最后 panic 在 `Failed to mount root device`。镜像里还没有系统分区，这是预期的结局。
  - 第 4 阶段、轮询模式（`p3-poll`，`fuxi-touch-poll=1`）：开始扫描成功；点一下屏幕，读到 `in1 mv8 up1`（一次按下、8 次移动、一次抬起），坐标 `2885,18595`，没有错误事件，所有 SPI 传输都成功。这是第一次在 XNU 里读到真实的触摸。
  - 第 4 阶段、中断模式（默认）：也通过了。`t4c-diag`（多一个 `armcpu-diagnostics=1`）读到 `in1 mv9 up1`、坐标 `1295,16685`、`irq11/0`；`t4b-touch` 第二次运行读到 `in1 mv8 up1`、坐标 `1635,19935`、`irq10/0`。每个触摸事件一次中断，没有误触发；FIFO 只读了十来次，轮询模式是 3531 次。
  - 两个触点（`t4b-touch` 第三次运行，从运行中的安卓用 `adb reboot bootloader` 切过来）：两根手指按住、抬起一根，读到 `in2 mv539 up1 c1`，剩下的触点在 `3095,15215`，`irq290/0`，没有误触发。
  - 一次没解释的重启：`t4b-touch` 第一次运行时，手机在内核启动几秒内自己重启回安卓，没有 panic 屏。同样的镜像之后又跑了两次，都正常，其中一次是从运行中的安卓启动的；`armcpu-diagnostics=1` 也没报出问题。所以是偶发的（开中断的 8 次启动里出现 1 次），原因未知。那一次是唯一一次在安卓之后手动按键进 fastboot 的，但只有一个样本，不能算原因；以后再遇到，要记下手机是怎么进 fastboot 的、之前在运行什么。
- **固件内存表修正**（2026-11-02，uefi-fuxi `c5793bc2`，设备仓库 `7407110`）：高端内存只保留两台实测手机上都是内存的两段（`0x880000000 + 0x39D00000`、`0x8C0000000 + 0x140000000`）。
  - 新旧固件比较：54 个模块里变了 46 个，正好是含这张表的 46 个。原因是调试控制台（`FrameBufferSerialPortLib`）要查 `"Display Reserved"`，几乎每个模块都链接了这张表。这些模块的 `.text` 里有 5859 条指令不同，全部只是立即数变了，操作码、寄存器和代码大小都没变。
  - 上机（镜像 `m1-touch`）：两根手指读到 `in2 mv221 up1 c1`、`irq113/0`，没有错误，也没有重启，内核管理的内存页数和旧固件下参数相同的那次启动一样。这次没有拍固件日志，所以新内存表是从镜像里读出来的，不是从屏幕上看到的。
- **多核**（2026-11-02，设备仓库 `680a818`，镜像 `s1-smp`、`s2-smp`、`s3-selfipi`）：`sheng-smp=1 armcpu-spi-ipi=1` 时 7 个副核都经 PSCI CPU_ON（smc）启动成功，各自进到第 7 步（运行），调度器认到 8 个核，触控线程跑在 3 号或 4 号大核上。
  - 不加 `armcpu-self-ipi=1` 时，内核一次 IPI 都没发出（`ipi0/0`）。XNU 给每个核的 `cpu_signal` 一开始就置上 SIGPdisabled，置着的时候不给它发 IPI，只有处理过一次 IPI 才清掉。XNU 指望平台的 CPU 初始化发出这第一个（自发给自己的 IPI，见 `osfmk/kern/machine.c` 的注释），ArmCpu 默认不发。加上之后每个核先给自己发一次，之后内核的 IPI 都能送到（85 个发出，3、4 号核各收 28、51 个）。
  - 1、2 号小核两次都没收到过时钟中断，说明它们启动了但没跑任何活。调度器会不会往这两个核上放任务，还不知道。
  - 多核下触控照常：中断 43、86、8 次，没有多余中断，没有错误。
- **触控电源对比**（`p4-power0`）：不投 RPMh 票时，复位三次加 4 线回退都收不到就绪事件，芯片 ID 读成 `00 00`，所以投票是必需的。
