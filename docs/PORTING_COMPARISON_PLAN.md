# UniXNU Fuxi 新旧工程对比与功能迁移方案（v2 · 学习 UniXNU-sheng 机制）

> 目标：把 `unixnu-fuxi-old` 已验证的存储能力，按 **`UniXNU-sheng`（新版 schema v2）的机制** 落到 `unixnu-fuxi-new`。
> 上游原则：`UniXNU-sm8550-common` 只读，严禁修改。
> 参考模板：`UniXNU-sheng`（已拉取到本地，作为结构/机制范本）。

---

## 0. 总原则：机制学 sheng，事实学 old

sheng 是官方 schema v2 参考实现。迁移不是把 old 的 v1 结构搬过来，而是：

~~~text
old 中已验证的【事实与驱动】 + sheng 的【结构机制】 = fuxi-new 的迁移结果
~~~

- 事实来源：old 的 `BUILD-PROGRESS.md`、`board.toml`、`NativeUfs` 驱动。
- 机制来源：sheng 的 `board.toml`(v2)、`.gitmodules`、`component:` 构建、`porting.toml`、`reports/`。

---

## 1. sheng 机制速查（我们要对齐的 7 条）

| # | sheng 的做法 | fuxi-new 现状 | 对齐动作 |
| --- | --- | --- | --- |
| 1 | 驱动是 git submodule，放 `drivers/<名>`，`.gitmodules` 记录 | 已有 `drivers/FuxiFtsTouch`；缺 UFS | 加 `drivers/NativeUfs` submodule |
| 2 | 驱动用 **component** 或 **设备脚本** 构建（`[kernel].archives` 可写 `component:X` 或 `build-*.py`） | fuxi 已用 component（ArmDTPlatform 等） | UFS 用设备脚本 `build-fuxi-ufs.py`，不改 fork catalog |
| 3 | defconfig 用 `CONFIG_XNU_*` 开关 | 已有 `fuxi_defconfig`；`CONFIG_XNU_NATIVE_UFS` 显式未设 | 打开 `CONFIG_XNU_NATIVE_UFS=y` |
| 4 | `[userdata]` 用十进制 LBA：`first_lba/last_lba/lba_bytes`，无 windows 数组 | fuxi-new 无 `[userdata]` | 补 `[userdata]`（十进制） |
| 5 | `[payload.adt]` 带 `root_match_volume_uuid`；boot-arg 用 `native-ufs-root=1` | fuxi-new 均缺 | 补 UUID + boot-arg |
| 6 | `porting.toml` 用 `[[area]] id="storage"` + `[[area.evidence]]` 记录 | storage area 已存在但 `status="planned"` | 更新为 `implemented`/真机后 `device-verified` |
| 7 | `reports/` 放日期化 bring-up 报告；`facts/` 放硬件事实 | fuxi-new 有 `facts/`，无 `reports/` | 补 `reports/` |

关键点：**sheng 的 `ipados-17.7.11-21H461` 配置段就是 fuxi 的直接模板**——fuxi-new 的 `os_profile` 也是 `ipados-17.7.11-21H461`，且 root 卷 UUID 相同（`04769D26-2CA0-4825-B443-E2E5F88300F2`）。

---

## 2. 关键事实对照（fuxi 用，来自 old 真机）

| 项 | 值 | 十进制（写进 [userdata]） |
| --- | --- | --- |
| UFS 主机控制器 | `0x1d84000` / `0x3000` | — |
| UFS PHY | `0x1d80000` / `0x2000` | — |
| GCC 时钟 | `0x100000` | — |
| apps_smmu | `0x15000000`，UFS stream `0x60` | — |
| compatible | `qcom,sm8550-ufshc` | — |
| userdata 起始 LBA | `0x2f7840` | `3110976` |
| userdata 末 LBA（修正后） | `0x3afc3fa` | `61880618` |
| lba_bytes | `4096` | `4096` |
| root 卷 UUID | `04769D26-2CA0-4825-B443-E2E5F88300F2` | — |
| chip-id | `0x207` | `"207"` |
| unique-chip-id | `0xce854c9ae043320b`（运行期注入，不落库） | — |

**boot-arg 语义**（来自 `NativeUFS-fuxi/NativeUfs.cpp:1747-1762`）：

~~~text
native-ufs-probe=N       只读/逐段验证（N=10 GPT、11 窗口、12 完整 startRoot + media 报告）
native-ufs-root=1        sheng 风格 root 路径（fuxi-new 采用这个）
native-fuxi-ufs-root=1   old fuxi 风格 root 路径（驱动仍兼容，但迁移后统一用 native-ufs-root）
~~~

---

## 3. 任务清单

> 进度总览（2026-11-03，14 commit 已落地）：
> - 任务 1（UFS 驱动接入）→ ✅
> - 任务 2（board.toml 对齐）→ ✅
> - 任务 3（defconfig + 存储组件接入）→ ✅
> - 任务 4（IOBlockStorageDevice 固定绑定）→ ✅
> - 任务 5（触控删光 Novatek）→ ✅
> - 任务 6（boot-log 完整链）→ ✅
> - 任务 7（分阶段 defer + 记录闭环）→ 🔄（porting.toml 已更新，facts/reports 待补）

### 任务 1：UFS 驱动以 submodule + 设备脚本接入（不改 fork catalog）✅

* **submodule**：`unixnu-fuxi-new/.gitmodules` 增加 `[submodule "drivers/NativeUfs"]`（url = `https://github.com/ljhhkx529/NativeUFS-fuxi.git`），`git submodule add/init/update`。
* **设备脚本**：`scripts/build-fuxi-ufs.py` 编译 `drivers/NativeUfs/NativeUfs.cpp` → `build/sheng-ufs/libShengUfs.a`（内核写死路径）。
* **tree 定位**：脚本反推 device checkout（通过 `drivers/FuxiFtsTouch` 软链接）定位 `drivers/NativeUfs`，因为 NativeUfs 不是组件、tree 不给它建软链接。
* **运行时类名**：保持 `NativeUfs` / `org.blu-sharky.NativeUfs`，不改名、不映射到 ShengUfs。

### 任务 2：board.toml 按 sheng 模板对齐 ✅

* `[userdata]`：`first_lba=3110976`、`last_lba=61880618`、`lba_bytes=4096`（十进制，无 windows 数组）。
* `[payload.adt]`：`root_match_volume_uuid = "04769D26-2CA0-4825-B443-E2E5F88300F2"`。
* `[payload].kernel_args`：追加 `native-ufs-root=1`。
* `[adt.defaults.u32]`：`sleep-disabled=1`、`vmm-present=1`、`"kern.maxvnodes"=78848`。

### 任务 3：defconfig + 存储组件接入 ✅

* `CONFIG_XNU_NATIVE_UFS=y` + `CONFIG_XNU_NATIVE_VIRTIO_BLOCK=y` + `CONFIG_XNU_NATIVE_VIRTIO_BLOCK_ARCHIVE`（verified-bundle）。
* `[components].include` 加 `VirtioMmioBlock`、`VerifiedRoot`。
* `[kernel].archives` 加 `component:VirtioMmioBlock`、`build-fuxi-virtio-bindings.py`、`build-boot-log.py`。

### 任务 4：IOBlockStorageDevice 固定绑定（代替 live audit）✅

* 搬 `scripts/data/native-storage-original-bindings.S`（11 个 21H461 kernelcache 固定地址）。
* `scripts/build-fuxi-virtio-bindings.py` 把 .S 编成 .o 追加进 Virtio verified-bundle archive。
* 不用 sheng 的 `build-virtio-mmio-bindings.py`（它依赖离线审计 `interface-audit.json`，fuxi 没有）。

### 任务 5：触控（删光 Novatek，保留 FTS）✅

* 旧 `NativeNovatekTouch`（NT36532E）：删光，不迁移。
* 新 `FuxiFtsTouch`（ST FTS，chip id `36 40`）：保留。

### 任务 6：boot-log 完整链 ✅

* 搬 `BootLog.c`、`BootCrashExport.c/h`、`BootLogTouchStats.c`、`BootLogFenceStubs.c`（真实源）。
* 补 `BootLogStubs.c`（GPU/display/touch 诊断占位）+ `BootLogExtraStubs.c`（buttons/process_wait/data_persist 占位）。
* 搬 `zzzc-boot-log.patch`（startup.c 调 `boot_log_tick(0)`）。
* `EXTRA_LD_ARCHIVES` 追加 `build/boot-log/libBootLog.a`。
* 注意：`NativeUFS-fuxi` 保留了 `boot_log_*` 强引用（ShengUfs 已删），所以 boot-log 是 fuxi 特有依赖。

### 任务 7：分阶段 defer + 记录闭环 🔄

* defer 项（阶段1 只做 UFS 只读链，挂 APFS root 时恢复）：
  * `RamBlock` + `CONFIG_XNU_NATIVE_RAM_BLOCK`
  * `VerifiedRoot` + `CONFIG_XNU_VERIFIED_ROOT_PROBE`
  * `boot-progress` + `CONFIG_XNU_BOOT_PROGRESS`（baseline 把它 gate 在 OWNER_ROOT_AUDIT 上）
* 记录：`porting.toml` storage area → `implemented`（真机后 `device-verified`）。
* 待补：`facts/ufs_facts.json` + `reports/` 日期化报告。

## 4. 实际执行步骤（14 commit 落地过程，含踩坑）

### 阶段 0：准备与基线
1. 确认内核 build 脚本对 UFS archive 的固定路径（`build/sheng-ufs/libShengUfs.a`）。
2. 记录 fuxi-new 基线：`bsd_init` → 触控 stage3/4 → PMGR bridge → `root device wait`。

### 阶段 1：UFS 驱动接入（commit 1、3、4）
3. `git submodule add …NativeUFS-fuxi.git drivers/NativeUfs`。
4. 写 `build-fuxi-ufs.py`（编译 NativeUfs.cpp → `build/sheng-ufs/libShengUfs.a`）。
5. **坑**：tree 不给非组件 NativeUfs 建软链接 → 脚本反推 device checkout（`drivers/FuxiFtsTouch` 软链接）定位源码。
6. **坑**：`verified_root.h` 找不到（VerifiedRoot/VirtioMmioBlock 不是组件）→ 反推 UniXNU fork 根用绝对路径。

### 阶段 2：board.toml + defconfig 对齐（commit 1、2、5）
7. `board.toml` 补 `[userdata]`、`root_match_volume_uuid`、`native-ufs-root=1`、`[adt.defaults.u32]`。
8. `fuxi_defconfig` 打开 `CONFIG_XNU_NATIVE_UFS=y` + `NATIVE_VIRTIO_BLOCK=y` + archive 变量。
9. `[components].include` 加 VirtioMmioBlock/VerifiedRoot；archives 加 `component:VirtioMmioBlock`。

### 阶段 3：存储依赖链 + 固定绑定（commit 5、6）
10. **坑**：`build-virtio-mmio-bindings.py` 依赖离线审计 `interface-audit.json`（GDB live capture，fuxi 没有）→ 改用 old 的 pinned `.S`。
11. 搬 `native-storage-original-bindings.S` + 写 `build-fuxi-virtio-bindings.py`（追加 11 个 IOBlockStorageDevice 绑定）。

### 阶段 4：boot-log 完整链 + stub（commit 5、10–14）
12. 搬 BootLog.c / BootCrashExport / BootLogTouchStats / BootLogFenceStubs。
13. **坑**：BootLog.c 引用几十个诊断页符号（GPU/display/touch/data_persist）→ 补 BootLogStubs.c + BootLogExtraStubs.c。
14. **坑**：StageAProbeStubs 与真实驱动、BootLogStubs 重复 → 只留真正缺的 data_persist 符号。
15. **坑**：`native_touch_edge_stats` 与 HID 重复 → 删 stub。
16. 搬 `zzzc-boot-log.patch`（startup.c 调 `boot_log_tick`）。
17. **坑**：`BootProgress.c` 缺 `Font.h` → 补搬。

### 阶段 5：分阶段 defer + 记录（commit 7、9）
18. defer RamBlock / VerifiedRoot / boot-progress（挂 APFS root 时恢复）。
19. **坑**：`build-xnu-4k-baseline.sh` 把 `BOOT_PROGRESS=1` gate 在 `OWNER_ROOT_AUDIT=1` 上 → 阶段1 关掉 boot-progress。
20. 更新 `porting.toml` storage area → `implemented`。

### 阶段 6：构建验证（待执行）
21. **坑（反复踩）**：改 defconfig 后必须重新 `./unixnu defconfig`，否则 `.config` 缓存旧值，链接缺符号。
22. `./unixnu defconfig fuxi_defconfig` + `./unixnu build kernel` 跑通链接。
23. 上机 `native-ufs-probe=10`（GPT 几何）→ `=12`（`published=2 reads>0 failures=0 media=6`）。
24. 通过后开 `native-ufs-root=1` + owner/VerifiedRoot/RamBlock/boot-progress，挂 APFS root。

---

## 5. 避坑要点（含实际踩的坑）

### 5.1 配置与构建

1. **改 defconfig 后必须重新 `./unixnu defconfig`**：build 读的是缓存的 `.config`，不重跑 defconfig 新配置不生效（反复踩过）。
2. **严禁改 `UniXNU-sm8550-common`**：UFS 特化全部收敛在 fuxi-new。
3. **UFS archive 输出到内核固定路径**：`build-fuxi-ufs.py` 产出 `build/sheng-ufs/libShengUfs.a`（`build-xnu-4k-baseline.sh` 写死），不改 fork components.toml。
4. **非组件驱动 tree 不建软链接**：NativeUfs / VerifiedRoot / VirtioMmioBlock 不是组件时，tree 里没有对应目录，脚本要反推 checkout 根用绝对路径。
5. **`BOOT_PROGRESS=1` 被 gate 在 `OWNER_ROOT_AUDIT=1`**：阶段1 只做 UFS 只读链，别开 boot-progress。

### 5.2 存储绑定

6. **sheng 的 `build-virtio-mmio-bindings.py` 依赖离线审计 `interface-audit.json`**：这是 GDB live capture 产物，不在仓库。fuxi 用 old 的 pinned `.S`（11 个 21H461 固定地址）替代。
7. **pinned .S 绑定 slide=-0x1000000 的 kernelcache**：换 OS pin / prelink slide 后地址失效，要重新审计。
8. **`NativeUFS-fuxi` ≠ `ShengUfs`**：前者保留 `boot_log_*` 强引用（ShengUfs 删了），所以 boot-log 是 fuxi 特有依赖，不能照搬 sheng 的"无 boot-log"配置。

### 5.3 boot-log stub

9. **BootLog.c 引用几十个诊断页符号**：GPU/display/touch/data_persist/buttons/process_wait 等，阶段1 没这些驱动，必须补 stub。
10. **stub 别搬 old 的 StageAProbeStubs 整份**：它假设这些子系统都不构建，会与真实驱动（UFS/HID/touch）重复符号。只抽真正缺的符号。
11. **stub 强定义会撞真实定义**：`native_touch_edge_stats` 在 HID 里有真实定义，BootLogStubs 里不能重复。fuxi 已构建的子系统，stub 里要去掉对应符号。

### 5.4 事实与参数

12. **boot-arg 统一用 `native-ufs-root=1`**（sheng 风格），不用 old 的 `native-fuxi-ufs-root`。
13. **last_lba 用修正值 `0x3afc3fa`（61880618）**，不用 old 的 `0x76923FA`。
14. **apps_smmu 缺口**：common dtsi 的 ufs 节点无 `iommus`、无 `apps_smmu`；驱动硬编码 `0x15000000`/stream `0x60`，走 DT matching 时需在 device 层补。
15. **触控删光 Novatek**：只保留 `FuxiFtsTouch`。
16. **禁止贴 GPL 驱动**：按硬件事实重封装。
