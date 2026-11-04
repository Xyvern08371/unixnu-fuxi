# fuxi 启动追踪（boot_track）

用色带探针逐步定位 XNU 启动卡点。色带从上到下：

| 色带 | 含义 | 状态 |
|---|---|---|
| 绿 | DarwinBoot 交接（UEFI） | ✅ |
| 蓝 | XNU 入口，MMU 关 | ✅ |
| 品红 | 即将打开 MMU | ✅ |
| 黄 | 当前探测点 | 见下 |

## 探测进度

| 探测点 | 结果 | 备注 |
|---|---|---|
| `_PE_create_console` 之后 | ✅ 有黄带 | 2026-11-04 确认走到控制台就绪；同时验证了 vinfo 虚拟地址画法 |
| `_bsd_init` 之后 | ✅ 有黄带 | 2026-11-04 确认 arm_init 走完、进入 bsd_init |
| AppleImage4（`_image4_dlxk_link` 返回） | ✅ 有黄带 | 2026-11-04 确认 AppleImage4 kext 启动并注册 API |
| `NativeUfs::probe` 入口 | ✅ 有黄带 | 2026-11-04 确认走到 root 挂载起点（AppleImage4 SecurityLock 已过） |
| `NativeRamBlock::start` 入口 | ✅ 有黄带 | 2026-11-04 确认走到 Data 卷挂载起点 |
| `_native_ram_block_volume_device` | ❌ 无黄带 | 该函数未被调用（不是卡点） |
| `_native_ram_block_volume_seed`（+0xC，参数校验后） | ✅ 有黄带 | 2026-11-04 确认 Data 卷挂载代码编译生效、volume_seed 被调用 |
| `_native_ufs_store_open` 入口 | ✅ 有黄带 | 2026-11-04 确认 selectVolumeSeed 找到 IOMedia、attachStore 开始打开 UFS store |
| `_native_ufs_store_read` 入口 | ✅ 有黄带 | 2026-11-04 确认 UFS store 打开成功、Data 卷开始被 APFS 读 |
| Data 卷 mount 调用（stage=2） | ✅ 有黄带（品红位置） | 2026-11-04 确认 copyout 完成、mount 被调用 |
| Data 卷 mount 返回（stage=3） | ✅ 有黄带（品红下一格） | 2026-11-04 确认 mount 成功返回 |
| Data 挂载完成（stage=4） | ✅ 有黄带（第五格） | 2026-11-04 Data 卷挂载全流程走通：volume_seed→copyout→mount→vnode_lookup→检查全过 |

## 问题点定位（2026-11-04）

**卡在 Data 卷挂载这一环：`NativeRamBlock::start` 之后，`native_ram_block_volume_seed` 阶段。**

- `NativeRamBlock::start` ✅ 有黄带 → 已进入 Data 卷驱动 start，`registerService()` 完成。
- `_native_ram_block_volume_device` ❌ 无黄带 → 该函数**根本没被调用**（不是卡点本身）。

原因：XNU 补丁 `offline-owner-systemos-mount.patch` 里 Data 卷挂载走的是 **`native_ram_block_volume_seed`**，不是 `native_ram_block_volume_device`。所以黄带挂错了函数。

真正要探测的是 `native_ram_block_volume_seed(DataUUID, ...)`：

```
Data 卷 UUID  = 3E81D4A6-8D16-496B-B890-E680C6E6997C  (CONFIG_XNU_OWNER_DATA_VOLUME_UUID)
root 卷 UUID  = 04769D26-2CA0-4825-B443-E2E5F88300F2  (board.toml root_match_volume_uuid)
```

`native_ram_block_volume_seed` → `selectVolumeSeed`：找 UUID 匹配的 IOMedia → `attachStore()`（打开 UFS 持久化窗口）→ `seedInfo()`。这一步失败/没走到，Data 卷就挂不上，系统停住。

黄带挂在 `native_ram_block_volume_seed` 的 **+0xC**（三条 `cbz` 参数校验之后、`str xzr,[x4]` 处），避免重放 PC-relative 的 `cbz`。

## 根因定位（2026-11-04）

**`native_ram_block_volume_seed` 没触发黄带，根因是 `CONFIG_XNU_OWNER_DATA_MOUNT` 没开。**

`fuxi_defconfig` 里 `# CONFIG_XNU_OWNER_DATA_MOUNT is not set`（注释说 Data mount 被推迟到 step 2b）。而 `native_ram_block_volume_seed` 的调用被 `#if defined(XNU_OWNER_DATA_MOUNT) && XNU_OWNER_DATA_MOUNT` 包裹，所以 Data 卷挂载代码根本没编译进内核 → 函数永远不被调用 → Data 卷挂不上 → 系统停住。

修复：`CONFIG_XNU_OWNER_DATA_MOUNT=y`（已提交 `77d0724`）。注意开启后 `build payload` 需要 `--data-ramdisk`。

## Data seed 生成（2026-11-04）

- `make-data-seed.py` 从 IPSW OS 镜像 `private/var` 生成 `data.dbr`（稀疏 APFS Data 卷）。
- 修了 `seed-data-grow.py`：APFS container 应匹配 `ContainerReference`，不是 `PhysicalStores`（提交 `ea2f999`）。
- 生成结果：`out/ipsw/21H461/data.dbr`，逻辑 220 GiB，稀疏约 1.1 MB，卷 UUID `E095FBF5-B5BA-43CE-ABD7-BF2618B0158C`（已绑定进 defconfig，提交 `393f138`）。

## 最终结果（2026-11-04）

**Data 卷挂载全流程走通（stage=4），系统进入 launchd 加载阶段。**

Data 挂载链：`volume_seed`（找 seed）→ `attachStore`（开 UFS store）→ `store_read`（Data 可读）→ `copyout`（挂载参数）→ `mount`（APFS 挂载成功）→ `vnode_lookup` + 设备/只读/APFS 检查全过 → `stage=4`。

stage=4 之后内核执行 `native_gpu_addon_prepare` / `native_staged_apps_prepare`，然后加载 `/sbin/launchd`。屏幕没有画面是因为 fuxi 未装 GPU addon（本项目目标本来就不需要它），不影响内核 + 用户态启动。

## 关键结论

- 黄带画法必须用 **XNU 的 `_vinfo`**（`v_baseaddr`/`v_rowbytes`/`v_height`），不能用 board 的 `_boot_progress_panic_vinfo`（`bp_panic_bind` 更晚才绑定）。
- 黄带挂 `bl SYMBOL` 调用点后时，cave 顺序必须是：**先 `bl callee`，再画黄带**（被探测函数内部才会建立画带所需的状态）。
- “SecurityLock LockCapsuleInterface” 出现在固件日志里是 UEFI `ExitBootServices` 的正常消息，不等于 XNU 走到了 AppleImage4。

## 启动顺序（arm_init 品红之后）

```
msr SCTLR_EL1          开 MMU
_arm_vm_init
_set_mmu_ttb
_processor_bootstrap
_arm_set_kernel_tbi
_cpu_data_init
_PE_init_platform
_configure_misc_apple_regs
_ml_parse_cpu_topology     (AMP 补丁已过)
_thread_bootstrap / _cpu_bootstrap / _rtclock_early_init ...
_serial_init
_kernel_startup_initialize_upto
_PE_create_console        ✅ 黄带已验证
_PE_init_printf
machine_startup
bsd_init                  ← 下一个探测点
AppleImage4 (image4_dlxk_link / SecurityLock)
root 卷挂载
Data 卷挂载 (NativeRamBlock)
```
