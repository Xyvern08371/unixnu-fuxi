# fuxi 引导链与交接约定

## 现在的两条链

```
出厂:   PBL → XBL(SBL) → ABL(LK) → boot.img ─┬─ kernel(Linux) + dtb + ramdisk
                                             └─ recovery / fastboot

WoA:    PBL → XBL(SBL) → ABL → boot.img(UEFI) → EDK2 DXE → BDS → bootmgfw.efi
```

## 我们要的链

```
PBL → XBL → ABL → boot.img(UEFI, 复用 Renegade) → EDK2 DXE → BDS
    → FuxiLoader.efi  ──[ ExitBootServices ]──>  payload (将来是 XNU)
```

关键认知：**"UEFI" 这一段不用我们写**，Renegade 那套已经能让 fuxi 进 DXE 并跑 `.efi`。
我们写的是 DXE 里的一个应用，负责最后 200 毫秒：准备设备树、装载载荷、交权。

## 三个交接点

| # | 交接 | 提供方 → 接收方 | 约定 / 现状 |
|---|---|---|---|
| 1 | ABL → UEFI | XBL/ABL → EDK2 | ABL 传 FDT 指针与内存布局；EDK2 自己建页表、开 cache、初始化 GICv3 与 generic timer。**已经有人替我们趟平** |
| 2 | BDS → 我们的 app | EDK2 → `FuxiLoader.efi` | 标准 UEFI 环境：Boot Services、`DeviceHandle` 指向 ESP、`Print` 可用。**这是我们现在站的位置** |
| 3 | app → payload | 我们 → XNU | `x0` = 设备树物理地址；其余通用寄存器清零；EL 与 MMU/cache 状态必须先定死 |

## 交接点 3 的细节（最容易翻车的地方）

XNU 的 arm64 入口对入口状态是有假设的，历史上所有"跳过去就静默重启"都出在这里：

- **异常等级**：Renegade UEFI 在骁龙上通常运行在 **EL2**，而 XNU 期望 **EL1**。
  若 `CurrentEL` 读出 2，跳转前必须自己配置 `HCR_EL2` 并 `eret` 降级，否则第一个
  `msr` 就 trap。
- **MMU / cache**：XNU 会自己建页表，但入口前 `SCTLR_EL1`（M/C/I 位）、`TTBR0/1`
  必须是它预期的值。安全做法是**跳转前关 MMU、关 D-cache、刷 I-cache**，让它从"干净"状态起步。
- **中断**：`daifset #0xf` 全关，GIC 由 payload 重新初始化。
- **设备树地址**：必须落在 XNU 能 identity-map 的低内存，且 8 字节对齐。
  用 `AllocatePages` 拿到的页在 UEFI 退出后依然有效（属于 `EfiLoaderData`，需要在
  内存图里保留，别被 payload 当空闲内存踩掉）。

这几条目前都是**待实测**，`loader/Loader.c` 里对应位置都留了注释。

## 上真机前必须实测确认的 6 件事

| # | 要确认的 | 怎么确认 | 不确认的后果 |
|---|---|---|---|
| 1 | `CurrentEL` 是 1 还是 2 | 我们的 app 第一行就打印 | 跳转即 trap |
| 2 | DRAM 基址 | 读真机 FDT 的 `/memory`，别信 profile 里的 `0x80000000` | 内核铺错地址 |
| 3 | ESP 路径规则 | 有些 UEFI 只认 `\EFI\BOOT\BOOTAA64.EFI` | 加载器压根不启动 |
| 4 | boot 分区偏移与 AVB | `fastboot getvar` + 看 vbmeta | 刷完不进系统 |
| 5 | 救砖通道 | 9008/EDL 是否可用、是否需要授权 | 变砖 |
| 6 | 无串口时的日志 | pstore/ramoops 是否在 UEFI 下可用 | 什么都看不见，纯盲调 |

## 风险

改 `boot` 分区等于放弃保修，且存在 hard brick 的可能。
**不要在唯一一台机器上做**，先确认第 5 条。
