# UniXNU Fuxi 新旧工程对比报告（v3 · 14-patch 状态）

> 生成时间：2026-11-03。反映 UFS 存储链 bring-up 的最新落地状态（14 个 commit）。
> 上游原则：`UniXNU-sm8550-common` 只读。

---

## 1. 三工程定位

| 工程 | 路径 | 角色 | 状态 |
| --- | --- | --- | --- |
| 旧单体工程 | `unixnu-fuxi-old` | 成熟功能源（schema v1） | UFS 全链路真机验证过，跑到用户态主屏，卡在 liveactivitiesd |
| 新架构工程 | `unixnu-fuxi-new-apex/unixnu-fuxi-new` | 迁移目标（schema v2） | 触控/CPU/内存/固件/打包已完成，UFS 存储链 14 patch 落地，差真机 probe 验证 |
| 上游公共层 | `UniXNU-sm8550-common` | 只读参考 | 提供 SoC DTS/config/kits/patches |

---

## 2. 已完成落地（14 个 commit）

| # | commit subject | 内容 |
| --- | --- | --- |
| 1 | add NativeUfs storage driver and board storage config | UFS 驱动 submodule + board.toml 存储配置 |
| 2 | read the platform seed from a CI secret | CI seed 走 secret |
| 3 | link NativeUfs into the build tree | 设备脚本反推 device checkout |
| 4 | resolve VerifiedRoot/VirtioMmioBlock headers by path | 头文件绝对路径 |
| 5 | add storage dependency chain | 组件 + boot-progress + boot-log |
| 6 | use pinned IOBlockStorageDevice bindings | 固定 .S 代替 live audit |
| 7 | defer RamBlock | 阶段1不需要 Data 卷 |
| 8 | port Font.h | boot-progress 字体表 |
| 9 | defer boot-progress | 避开 OWNER_ROOT_AUDIT gate |
| 10 | add BootLogStubs | boot-log 诊断占位符 |
| 11 | cover remaining boot-log stubs | StageA + Extra stubs |
| 12 | drop StageA keep missing stubs | 只保留真正缺的占位符 |
| 13 | drop touch edge-stats stub | 删与 HID 重复的符号 |
| 14 | add boot-log call site | startup.c 调 boot_log_tick |

对应 patch 文件：`0001`–`0014`。

---

## 3. 关键决策（区别于 sheng 的旧 17.7.11 路线）

1. **UFS 驱动走设备脚本，不改 fork components.toml**：fork 只有 `ShengUfs` 组件（`legacy_name=NativeUfs`），没有 `id=NativeUfs`。用 `component:NativeUfs` 会触发 legacy 映射回 ShengUfs。所以 fuxi 用 `scripts/build-fuxi-ufs.py` 直接编译 `drivers/NativeUfs`（submodule），运行时类名保持 NativeUfs。

2. **IOBlockStorageDevice 绑定用 old 的固定 .S**：sheng 的 `build-virtio-mmio-bindings.py` 依赖离线审计 `interface-audit.json`（GDB live capture），fuxi 没有。old fuxi 已经把这套地址固化成 `native-storage-original-bindings.S`（11 个符号），直接复用。

3. **阶段1 只做 UFS 只读链**：VerifiedRoot / RamBlock / boot-progress 三者 defer，因为它们要么需要签名 policy、要么被 baseline 脚本 gate 在 `OWNER_ROOT_AUDIT` 上，都属于挂 APFS root 阶段。

---

## 4. 功能完整度对照

| 功能 | old 状态 | new 状态 | 差距 |
| --- | --- | --- | --- |
| 触控 | ✅ Novatek | ✅ FTS（implemented） | new 更好 |
| CPU/SMP | — | ✅ implemented | new 对齐 |
| 内存 | — | ✅ implemented | new 对齐 |
| 固件 | ⚠️ | ✅ host-verified | new 对齐 |
| 打包 | — | ✅ device-verified | new 领先 |
| PMGR/power | 部分 | ✅ implemented（bridge） | new 对齐 |
| UFS 存储 | ⚠️（真机验证过读路径） | 🔄 implemented（差真机 probe） | 进行中 |
| 显示 | ⚠️ | ❌ planned | 完全没做 |
| GPU/Metal | ⚠️ | ❌ planned | 完全没做 |
| USB 调试 | ⚠️ | ❌ | 没做（Task4） |
| Data 持久化 | ⚠️ | ❌ defer | 没做（阶段2） |
| 音频/网络/传感器/电池 | ❌ | planned | 双方基本没做 |

---

## 5. 剩余差距（按优先级）

### P0 — 阶段1 收尾

1. 链接跑通 + 真机 `probe=10/12` 验证。
2. `read-sheng-log.py` 未搬（probe 通过后无串口读日志需要）。
3. `sheng-log=1` boot-arg 未加（boot-log 启用参数）。

### P1 — 阶段2 挂 APFS root

4. VerifiedRoot + 签名 policy bundle。
5. RamBlock + `build-userdata-root-image.py` + `seed-data-skip-setup.py`。
6. boot-progress 恢复（`BOOT_PROGRESS=y` + archive）。
7. `offline-owner-systemos-release-launchd.patch`（device 层缺失）。

### P2 — 阶段3 用户态 UI

8. 显示链：NativeLegacyDisplay / DPU / Framebuffer / Backlight / OfflineGOP。
9. GPU/Metal 链：Adreno 探针 / GpuPowerProbe / OfflineMetal / OriginalMetal / RenderBox。
10. USB 调试：QcomXnuUsbDebug + FuxiUsbCompat + zzzd patch。

### P3 — 质量保障

11. `check-*` host 校验脚本（old 60+，new 只有 ci/ 3 个）。
12. `check-fuxi.py` 板级 preflight。

---

## 6. patch 四层归属（old 57 patch → 新架构）

| 层 | 位置 | 数量 |
| --- | --- | --- |
| arch | UniXNU fork `profiles/arch/arm64/patches/xnu/series` | 54 |
| os | fork `profiles/os/ipados-17.7.11-21H461/patches/xnu/series` | 3 |
| soc | `sm8550-common/patches/xnu/series` | 2 |
| device | `new/patches/xnu/series` | 3（zzyf-sheng-amp、fuxi-touch-probe、zzzc-boot-log） |

仍缺失 device patch：`offline-owner-systemos-release-launchd`（阶段2）、`zzzd-fuxi-usb-debug`（Task4）。

---

## 7. package 子系统归属（old 110+ 文件）

| 子系统 | new 状态 |
| --- | --- |
| GPU/Adreno 底层 | ✅ 组件化（Adreno740 + sm8550-common kits） |
| 触控 | ✅ 新版 FTS 替代 |
| boot 诊断 | ⚠️ 部分搬 + 部分 stub + 部分 defer |
| 显示/DPU | ⏸️ 阶段2/3 |
| Metal/GPU 用户态 | ⏸️ 阶段3 |
| 平台（按键/USB/cpufreq） | ⏸️ 未搬（buttons stub 占位） |
| 音频/I2C | ⏸️ 阶段3 |

---

## 8. 结论

- **项目完整度**：new 是阶段1 精简版，old 是完整 bring-up。缺的 ~90 package 文件、~140 scripts 属于显示/GPU/Metal/USB/Data/音频，不是 UFS 存储链遗漏。
- **功能完整度**：三层递进缺口——UFS 只读链（差真机验证）、挂 APFS root（四件套全缺）、用户态 UI（全套未搬）。
- **当前最该做**：先把 14 patch 应用到构建 checkout，跑通链接 + probe=10/12；同时补 `read-sheng-log.py` 和 `sheng-log=1`，这是无串口环境验证 UFS 的必要配套。
