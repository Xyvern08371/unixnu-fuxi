# UniXNU fuxi（小米 13）

小米 13（代号 `fuxi`）的 UniXNU 设备支持，SoC 为高通 SM8550。设备配置选择
[UniXNU-sm8550-common](https://github.com/UniXNU/UniXNU-sm8550-common) 共享平台，
以及 `ipados-17.7.11-21H461` OS 配置（iPadOS 17.7.11 / 21H461）。

> 说明：本设备沿用了共享 SM8550 平台（sheng）的组件与启动参数 ABI，因此代码里
> `ShengUfs`、`ShengHidInput`、`ShengNovatekTouch`、`sheng-wifi=5`、`sheng-gpu-*`
> 等名称保持不变——它们是内核/驱动约定的接口名，改名会导致内核不识别。

## 目录结构

| 路径 | 内容 |
| --- | --- |
| `porting.toml` | 各子系统输入、发现、证据与完成条件 |
| `board.toml` | 设备配置与组件选择 |
| `feeds.toml` | 固定的 SoC 源码引脚 |
| `configs/fuxi_defconfig` | 设备内核配置 |
| `dts/fuxi.dts` | 内存、CPU 选择与外设配置 |
| `patches/xnu/series` | 板级补丁 |
| `proprietary-files.txt` | 固件输入路径 |
| `package/` | 设备策略、显示、输入与诊断 |
| `scripts/` | 设备构建与检查工具 |
| `local-tools/` | 本地固件打包工具（如 `make-wifi-fw.py`） |

`Adreno740` 与 `AdrenoMetal` 提供 GPU 实现。共享 GMU、命令数据库与 GPU SMMU 操作在
SoC 仓库的 `Sm8550Platform` kit 中。fuxi 提供 GPU 投票、签名 ZAP 固件、保留内存与
显示集成；GPU 初始化使用 staged platform build。硬件 DTS 包含 GPU 资源；ADT 通过
`unixnu,adt-name` 导出节点。

`ShengUfs` 负责设备存储与持久化策略。`ShengHidInput` 与 `ShengNovatekTouch` 提供输入
集成。`QcomGeniSpi` 提供共享 SPI 控制器接口。`Ath12kWifi` 通过板级 PCIe、MSI、DMA 与
网络接口提供 Wi-Fi 栈。payload 卷为 208 MiB。设备选择 sRGB 显示属性与 120 Hz 显示时序。

## 开发记录

每次子系统改动都要维护 [porting.toml](porting.toml)，记录硬件、配置、流程、发现、证据
与完成条件。设备页在 <https://unixnu.com/zh/devices/fuxi> 渲染这份记录。维护者与代理遵循
同一份[记录指南](https://unixnu.com/zh/porting/records)。`Porting record` CI 检查会校验
结构、组件覆盖，以及改动代码时发现/证据的更新。

本仓库拥有 ShengUfs、ShengHidInput、ShengNovatekTouch、ShengPreflight 子模块。
共享组件来自所选配置与 UniXNU 目录。改存储资源或策略前先读
[UFS 指南](https://unixnu.com/zh/porting/ufs)。

## 构建

固件必须内嵌 UniXNU、UniXNUDxe、DarwinBoot 与共享 `UniXNURamDiskDxe`，并带 DiskIoDxe
和 FAT 支持。这些模块负责暴露 payload 配置与启动项。见
[固件集成](https://unixnu.com/zh/porting/uefi-firmware#required-integration)。

在 UniXNU 仓库根目录执行：

```sh
./unixnu defconfig fuxi_defconfig --device ../unixnu-fuxi
./unixnu fetch --device ../unixnu-fuxi
./unixnu status --device ../unixnu-fuxi --json
./unixnu build kernel --device ../unixnu-fuxi --kernelcache /path/to/kernelcache
./unixnu build firmware --device ../unixnu-fuxi --uefi ../uefi-fuxi
./unixnu build payload --device ../unixnu-fuxi --unique-chip-id "$UNIXNU_UNIQUE_CHIP_ID" \
  --data-ramdisk /path/to/data.dbr --trust-cache /path/to/trustcache
./unixnu bootimg --device ../unixnu-fuxi --uefi ../uefi-fuxi --dtb /path/to/firmware.dtb
```

输出在 `out/fuxi/ipados-17.7.11-21H461/fuxi/` 下。payload 步骤编译硬件 DTS 并写出
`kernel.macho.adt`。boot image 用 `--dtb` 接收固件的 FDT。

构建输入包括选定的 kernelcache、验证根策略、厂商固件、生成的 GPU 寄存器/电源头、
UEFI 源码，以及 payload 使用的 Data 与 trust-cache 输入。二进制输入保存在本地缓存。
UniXNU 里的 `scripts/data/adreno-inputs.json` 记录 GPU 固件引脚。

## 文档

文档站维护在 UniXNU：

- [fuxi 设备指南](https://unixnu.com/zh/devices/fuxi)
- [构建](https://unixnu.com/zh/building)
- [设备仓库规范](https://unixnu.com/zh/porting/device-repository)
- [设备树规范](https://unixnu.com/zh/porting/device-tree)
- [组件目录](https://unixnu.com/zh/reference/components)
- [迁移指南](https://unixnu.com/zh/porting/migration)

构建结果与设备的 boot、存储、显示、输入、GPU 观察要分别记录，并附源码版本与命令。

## 本地构建输入

在 UniXNU 仓库根目录的 `unixnu.local.toml` 里保存设备路径与启动参数，见
[配置参考](https://unixnu.com/zh/reference/configuration#local-build-inputs)。
然后使用 `./unixnu kernel`、`./unixnu firmware`、`./unixnu payload`、`./unixnu bootimg`。
改动参数需要重新构建 payload 和 boot image。见
[启动参数](https://unixnu.com/zh/xnu/boot-arguments#apply-arguments) 与
[绿条诊断](https://unixnu.com/zh/guide/debugging#green-bar)。
