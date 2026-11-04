# UNDO / 恢复清单

记录为「分阶段 bring-up」故意做的临时取舍，以及将来如何恢复。每一项都对应一个已提交的改动。

---

## 1. VerifiedRoot 延迟（阶段 1 只做 UFS 只读链）

### 当前状态（已落地，commit 8e7f9cb）

- `[components].include` **仍保留** `"VerifiedRoot"`。
- `configs/fuxi_defconfig` 里 `CONFIG_XNU_VERIFIED_ROOT_PROBE` **关闭**（注释为 not set）。
- `CONFIG_XNU_VERIFIED_ROOT_ARCHIVE` 已删除。
- `scripts/build-fuxi-ufs.py` 编译 NativeUfs **不带** `-DNATIVE_VERIFIED_BLOCK=1`，也不 include `kits/VerifiedRoot/include`。
- `scripts/build-fuxi-virtio-bindings.py` 只追加 pinned 的 `IOBlockStorageDevice` 绑定，不引入 vr_* 符号。

### 为什么这样

第一阶段目标是 `native-ufs-probe=10/12` 的 UFS 只读验证：读 GPT、读窗口、发 media 报告。这个阶段不需要挂 APFS root，也就不需要：

- `vr_*` / `verified_root_*` 符号（由 VerifiedRoot 提供）
- 签名的 root policy bundle
- VerifiedRoot 的运行时校验路径

开着它只会无谓地拉入一套依赖，还可能在链接时强拉 `vr_*` 符号。所以先关掉，最小化第一阶段变量。

### 何时恢复

`probe=10` 验证 GPT 几何、`probe=12` 验证 `published=2 reads>0 failures=0 media=6` 都通过后，要进入 `native-ufs-root=1` 挂 APFS root 时，再恢复 VerifiedRoot。

### 恢复步骤（撤销本取舍）

1. **defconfig** 打开：

   ```text
   CONFIG_XNU_VERIFIED_ROOT_PROBE=y
   CONFIG_XNU_VERIFIED_ROOT_ARCHIVE="{tree}/build/verified-root-os-xnu-bundle/libVerifiedRootProbe.a"
   ```

2. **build-fuxi-ufs.py** 恢复 verified 编译（`ufs_extra`）：

   ```python
   '-I', unixnu / 'kits/VerifiedRoot/include',
   '-DNATIVE_VERIFIED_BLOCK=1',
   '-DNATIVE_VERIFIED_BLOCK_MULTI_POLICY=1',
   ```

3. **准备 VerifiedRoot 输入**：
   - 签名的 OS/SystemOS policy bundle（对应 iPadOS 17.7.11 21H461）。
   - 让 `build-verified-root-probe.py` 能产出 `libVerifiedRootProbe.a`（走 `-component os` → `build/verified-root-os-xnu-bundle`）。
   - 确认 `board.toml` 里 VerifiedRoot 的 policy 输入路径和 sheng 对齐。

4. **验证**：`native-ufs-root=1` 上机，确认越过 `root device wait`，`Failed to mount root device` 消失。

---

## 2. boot-log 保留（NativeUFS-fuxi 特有依赖）

### 当前状态（commit 173c0d0）

- 从 old fuxi 搬入 `package/BootLog.c`、`BootCrashExport.c/h`、`BootLogTouchStats.c`、`BootLogFenceStubs.c`。
- `scripts/build-boot-log.py`（`kits/sheng` → `kits/fuxi`）。
- `configs/fuxi_defconfig` 的 `CONFIG_XNU_EXTRA_LD_ARCHIVES` 追加 `{tree}/build/boot-log/libBootLog.a`。

### 为什么

`NativeUFS-fuxi`（不同于 `ShengUfs`）在 `NativeUfs.cpp` 保留了 `boot_log_state/rounds/errors/first_lba` 的**强引用**，链接必须有定义。old fuxi 用 BootLog 提供这些符号。

### 何时可移除

如果哪天 fuxi 切换到 `ShengUfs`（它没有这些 boot_log 引用），或者决定砍掉 UFS 日志通道，才能移除这一整套。

### 移除步骤

- 删除 `package/BootLog.c`、`BootCrashExport.*`、`BootLogTouchStats.c`、`BootLogFenceStubs.c`。
- 删除 `scripts/build-boot-log.py`。
- `board.toml [kernel].archives` 删 `build-boot-log.py`。
- `configs/fuxi_defconfig` 的 `EXTRA_LD_ARCHIVES` 删 `{tree}/build/boot-log/libBootLog.a`。

---

## 3. boot-progress 延迟

### 当前状态（commit c0875ef）

- `package/BootProgress.c` + 4 个头 + `BootFaultProbe.c` + `BootWatchdogPolicy.c` + `Font.h` **已搬入但未编译**。
- `scripts/build-boot-progress.py` 已搬入，但从 `[kernel].archives` 移除。
- `CONFIG_XNU_BOOT_PROGRESS` **关闭**（not set）。

### 为什么

`build-xnu-4k-baseline.sh` 里 `BOOT_PROGRESS=1` 被 gate 在 `XNU_OWNER_ROOT_AUDIT=1` 上，而阶段 1 不开 owner-root。且 `NativeUfs.cpp` 对 `boot_progress_poll()` 是 weak 引用，不定义也能链接。

### 何时恢复

挂 APFS root 时，和 `OWNER_ROOT_AUDIT` / `VerifiedRoot` / `RamBlock` 一起恢复：`CONFIG_XNU_BOOT_PROGRESS=y` + `[kernel].archives` 加回 `build-boot-progress.py`。

---

## 4. pinned IOBlockStorageDevice 绑定（代替 live audit）

### 当前状态（commit 8e7f9cb）

- `scripts/data/native-storage-original-bindings.S`（11 个 21H461 kernelcache 固定地址）。
- `scripts/build-fuxi-virtio-bindings.py` 追加到 Virtio archive。
- 不再用 sheng 的 `build-virtio-mmio-bindings.py --component VirtioMmioBlock`。

### 为什么

sheng 的 bindings 脚本依赖离线审计 `build/storage-abi/interface-audit.json`（GDB live capture），fuxi 没有该产物。old fuxi 已经把这套地址固化成 `.S`，直接复用。

### 何时/如何换回

如果以后拿到 sheng 的 `interface-audit.json` 及其前置产物（gdb-stop、aes-interface-audit），可以：

- `board.toml` 把 `build-fuxi-virtio-bindings.py` 换回 `build-virtio-mmio-bindings.py --component VirtioMmioBlock`。
- 删除 `scripts/build-fuxi-virtio-bindings.py` 和 `scripts/data/native-storage-original-bindings.S`。

### 注意

`.S` 里的地址绑定的是 **slide=-0x1000000 的 21H461 kernelcache**（sha256 `f18b4df8…`）。如果 kernelcache pin 变了（换 OS 版本 / prelink slide），这套地址会失效，必须重新审计或重新提取。

---

## 5. CI platform seed 走 secret（不是 hardcode）

### 当前状态（commit 99391b1）

- `.github/workflows/build.yml` 里 `DEVICE_SEED: ${{ secrets.UNIXNU_UNIQUE_CHIP_ID }}`。
- 真机 seed 不在 git 历史里。

### 为什么

platform seed 是单机唯一身份，用于 data 卷密钥派生，不能进公开仓库。

### 使用要求

- 仓库 Settings → Secrets 里配 `UNIXNU_UNIQUE_CHIP_ID`。
- 换设备时只改 secret，不改代码。

---

## 6. 控制集合颗粒度对照（stub ↔ 真实源）

阶段 1 把 old fuxi 的"细粒度真实源"降成两个粗粒度 stub 文件（`BootLogStubs.c` + `BootLogExtraStubs.c`）。下面是每个 stub 符号对应的 old 真实源，以及阶段 2 何时替换。

### 6.1 已搬入且编译的真实源（不需 stub）

| 文件 | 提供 |
| --- | --- |
| `BootLog.c` | `boot_log_tick`、`boot_log_state/rounds/errors/first_lba`（**强引用，必需**） |
| `BootCrashExport.c/h` | CrashReporter 快照导出 |
| `BootLogTouchStats.c` | touch 计数器 |
| `BootLogFenceStubs.c` | fence 事件占位 |

### 6.2 BootLogStubs.c 的 stub ↔ 真实源

| stub 符号 | old 真实源 | 阶段 2 何时替换 |
| --- | --- | --- |
| `boot_progress_page_text/banner_text/banner_rows/ext/ext_wide/panic_text` | `BootProgress.c` | 恢复 boot-progress 时 |
| `boot_progress_tag/profile_rows` | `BootProgress.c` | 同上 |
| `native_gop_wait_stats` | `LegacyDisplayProbe.cpp`（legacy display） | 接 legacy display 时 |
| `native_adreno_*`（约 30 个） | `GpuPowerProbe.cpp` / `NativeAdrenoSubmit.cpp`（Adreno） | 接 Adreno 时 |
| `native_touch_strokes/stroke_count/extent` | `TouchProbe.cpp`（旧 Novatek） | **不替换**——fuxi 用 FTS，这些旧 Novatek 计数器永远不再有真实源，保留 stub 即可 |
| `native_dpu_stats/pipes/more` | `DisplayTimingProbe.cpp`（DPU） | 接 DPU 时 |
| `native_cpufreq_row` | `CpuFreqProbe.cpp` | 接 cpufreq 诊断时 |
| `native_gpu_idle_*` / `native_gpu_perf_vote` | `GpuPowerProbe.cpp` | 接 Adreno 时 |
| `boot_ui_trace_role_rows/hot_rows` | `BootUiTraceProbe.c` | 接 UI trace 时 |
| `native_legacy_*`（properties_now/clients_dump/swap_timeline/prepare_report/state_words） | `LegacyDisplayProbe.cpp` | 接 legacy display 时 |
| `boot_reset_probe/bootloader` | `BootReset.c` | 接复位诊断时 |

> 注意：`native_touch_edge_stats` 本来在 BootLogStubs 里，但 fuxi 已构建 HID（`libShengHidInput.a` 有真实定义），已删除（commit f6e99a1）。

### 6.3 BootLogExtraStubs.c 的 stub ↔ 真实源

| stub 符号 | old 真实源 | 阶段 2 何时替换 |
| --- | --- | --- |
| `fuxi_buttons_stats` | `FuxiButtons.cpp` | 接按键诊断时 |
| `native_process_wait_port` | `BootProcessProbe.c` | 接进程遍历诊断时 |
| `native_data_persist_*`（12 个） | `NativeRamBlock.cpp`（RamBlock 持久 Data） | 恢复 RamBlock 时 |

### 6.4 已删除 / 未搬入的 old 文件（阶段 1 不需要）

| old 文件 | 说明 |
| --- | --- |
| `StageAProbeStubs.c`（94 符号） | 整体不搬；只抽了 `native_data_persist_*` 12 个进 ExtraStubs。其余符号要么真实驱动有、要么 BootLogStubs 已有，搬了会撞重复 |
| `StageAStorageStubs.c` | 阶段 A 存储 stub，v1 遗留，v2 不需要 |
| `BootProgressShim.c` | boot-progress 关闭时的 no-op shim；boot-progress 已 defer，不需要 |
| `BootReset.c / BootResetCore.h` | 复位诊断，阶段 1 无 |
| `BootUiTraceProbe.c / BootUiTraceCore.h / BootUiTraceDetails.h` | UI trace，阶段 1 无 |
| `BootProcessProbe.c` | 进程遍历，阶段 1 无 |
| `FuxiButtons.cpp` | 按键，阶段 1 无 |
| `FuxiUsbCompat.c` | USB 调试适配，Task 4 可选 |

---

## 7. patch 四层归属（old 57 个 patch → 新架构）

old fuxi 的 `patches/xnu/` 有 57 个 patch，新架构把它们分到四层。**device 层只需要 fuxi 特有的，其余由 arch/os/soc 层覆盖，不要重复搬。**

| 层 | 位置 | 覆盖的 old patch |
| --- | --- | --- |
| arch（arm64 通用） | UniXNU fork `profiles/arch/arm64/patches/xnu/series` | 54 个：apple-only-cpu-tunables、architectural-timer-entry、armvirt-platform-personality、cxx-flag-dependencies、disabled-deferred-reclaim、external-archive-dependencies、kernel-sdk-root、local-availability、mockfs-*（5）、native-4k-*（3）、native-aes-personality、native-arm-pan、native-dt-panic-region、native-lookup-trace、native-priv-work-interval、native-quiet-managed-page-report、native-text-fixup、native-trust-cache-runtime、native-union-*（2）、native-work-interval-*（3）、non-apple-*（3）、null-root-media、offline-component-load-probes、offline-legacy-start、offline-native-gpu-broker、offline-owner-*（6，不含 release-launchd）、offline-pgz-alignment-probe、pgz-aligned-validation、public-entitlements-header、published-freezer-condition、source-*（3）、zzw/zzwb/zzx/zzy/zzzy/zzzb/zzzc 系列 |
| os（ipados-17.7.11） | fork `profiles/os/ipados-17.7.11-21H461/patches/xnu/series` | `zzz-boot-progress` + XnuPrelink 组件 2 个 |
| soc（sm8550） | `UniXNU-sm8550-common/patches/xnu/series` | `native-smp-secondary`、`sheng-platform-power` |
| device（fuxi 特有） | `unixnu-fuxi-new/patches/xnu/series` | `zzyf-sheng-amp`、`fuxi-touch-probe`、`zzzc-boot-log` |

### 7.1 仍缺失的 device 层 patch

| patch | 用途 | 状态 |
| --- | --- | --- |
| `zzzc-boot-log.patch` | startup.c 调 `boot_log_tick(0)`，启用 UFS 日志写线程 | ✅ 已补（commit 9e25526） |
| `offline-owner-systemos-release-launchd.patch` | owner SystemOS launchd 释放 | ⏸️ 阶段 2（挂 owner SystemOS 时补） |
| `zzzd-fuxi-usb-debug.patch` | fuxi USB 调试（QcomXnuUsbDebug） | ⏸️ Task 4 |

> 注意：old 的 `zzzc-boot-log.patch` 上下文依赖 `boot_progress_start()`（由 os 层 `zzz-boot-progress.patch` 提供）。即使 `CONFIG_XNU_BOOT_PROGRESS` 关闭，该调用点仍存在（宏展开为 no-op），所以 patch 能正常应用。

---

## 8. package 子系统归属（old 100+ 文件 → 新架构）

| 子系统 | old 文件 | new 状态 |
| --- | --- | --- |
| GPU/Adreno | AdrenoCompilerProbe、AdrenoFirmwareProbe、AdrenoPM4Probe、GpuPowerProbe、ShengGmu、ShengGpuSmmu、SmmuBypass、ArmSmmu4KProbe 等（~20） | ✅ 组件化：`component:Adreno740` + `sm8550-common/kits/Sm8550Platform` 覆盖 |
| 显示/DPU | DisplayTimingProbe、LegacyDisplay*、Framebuffer*、OfflineGOP*、BacklightProbe、AppleARMBacklight 等（~30） | ⏸️ 阶段 2/3 |
| Metal/GPU 用户态 | OfflineMetal*、OriginalMetal*、OriginalGPU*、OriginalRenderBox*、HostMetalDiagnostic 等（~30） | ⏸️ 阶段 3 |
| boot 诊断 | BootLog/BootProgress/BootWatchdogPolicy/BootProcessProbe/BootReset/BootUiTrace/BootCrashExport 等（~20） | ⚠️ 部分搬（见 §6），部分 stub，部分未搬 |
| 触控 | TouchProbe、Ftm5Touch、TouchBoard、HidInput*（~8） | ✅ 新版 `FuxiFtsTouch` + `FuxiTouchProbe` + `NativeHidInput` 替代，old 删除 |
| 平台 | FuxiButtons、FuxiUsbCompat、FuxiDpuScanoutStubs、CpuFreqProbe、KeyStoreProbe、ConstantUploadsProbe 等（~10） | ⏸️ 未搬（buttons 用 stub 占位） |
| 音频/I2C/其他 | GeniI2c、Cs35l43 等（~10） | ⏸️ 阶段 3 |

---

## 附：当前完整 patch 链

```text
0001-fuxi-add-nativeufs-storage-driver.patch
0002-fuxi-read-platform-seed-from-ci-secret.patch
0003-fuxi-link-nativeufs-into-build-tree.patch
0004-fuxi-resolve-verifiedroot-headers-by-path.patch
0005-fuxi-add-storage-dependency-chain.patch
0006-fuxi-pinned-storage-bindings-no-audit.patch
0007-fuxi-defer-ramblock.patch
0008-fuxi-port-font-h.patch
0009-fuxi-defer-boot-progress.patch
0010-fuxi-add-bootlogstubs.patch
0011-fuxi-cover-remaining-bootlog-stubs.patch
0012-fuxi-drop-stagea-keep-missing-stubs.patch
0013-fuxi-drop-touch-edge-stats-stub.patch
0014-fuxi-add-boot-log-call-site.patch
```
