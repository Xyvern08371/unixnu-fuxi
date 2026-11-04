# Task 1：UFS 存储驱动接入（完整记录 · 14-patch 状态）

> 目标：把已验证的 fuxi NativeUfs 存储驱动接入 `unixnu-fuxi-new`，解除 `root device wait` 阻塞。
> 结论：**不改 OddlyLabs/UniXNU 的 components.toml**，走「submodule + 设备脚本 + 固定绑定」路线，运行时类名保持 `NativeUfs`。

---

## 1. 方案决策

UniXNU 的 `[kernel].archives` 支持两种条目：

~~~text
component:<ID>   官方组件配方（需要 fork components.toml 有该组件）
build-*.py       设备仓库自己的脚本
~~~

核查：fork 的 UFS 组件只有 `ShengUfs`（`legacy_name=NativeUfs`），**没有 `id=NativeUfs`**。硬用 `component:NativeUfs` 会被 legacy 规则路由回 ShengUfs。因此：

- UFS 驱动 = `drivers/NativeUfs` submodule（`ljhhkx529/NativeUFS-fuxi`）。
- 编译 = `scripts/build-fuxi-ufs.py`（设备脚本）。
- IOBlockStorageDevice 绑定 = old 的固定 `.S`，不走 interface-audit。

---

## 2. 最终落地清单（14 commit）

| commit | 内容 |
| --- | --- |
| `8c07d1d` | `drivers/NativeUfs` submodule + `board.toml` 存储配置 + `CONFIG_XNU_NATIVE_UFS=y` |
| `99391b1` | CI platform seed 走 secret（独立功能） |
| `de26af5` | `build-fuxi-ufs.py` 反推 device checkout 定位 `drivers/NativeUfs` |
| `a69f5f7` | VerifiedRoot/VirtioMmioBlock 头文件绝对路径 |
| `173c0d0` | 存储依赖链：VirtioMmioBlock/RamBlock/VerifiedRoot 组件 + boot-progress + boot-log |
| `8e7f9cb` | 固定 .S 绑定（`native-storage-original-bindings.S`）+ 关闭 VERIFIED_ROOT_PROBE |
| `0a1dc35` | 延迟 RamBlock |
| `c900844` | 补 Font.h |
| `c0875ef` | 延迟 boot-progress |
| `b79f40c` | 补 BootLogStubs |
| `8b3a683` | 补 StageA + Extra stubs |
| `b7d5d4e` | 删 StageA 只留精简 stub |
| `f6e99a1` | 删重复 touch edge-stats |
| `9e25526` | 补 `zzzc-boot-log.patch`（startup.c 调 boot_log_tick） |

---

## 3. 构建脚本 `build-fuxi-ufs.py`

编译 `drivers/NativeUfs/NativeUfs.cpp` → `build/sheng-ufs/libShengUfs.a`（内核写死的 UFS archive 路径）。

include/define（阶段1 非 verified）：

~~~text
-I .cache/xnu-work/osfmk
-I build/storage-abi/include
-I <unixnu>/drivers/VirtioMmioBlock
-mgeneral-regs-only
~~~

---

## 4. 内核链接机制

`build-xnu-4k-baseline.sh` 在 `CONFIG_XNU_NATIVE_UFS=y` 时 force-load `build/sheng-ufs/libShengUfs.a`；`CONFIG_XNU_NATIVE_VIRTIO_BLOCK=y` 时 force-load `build/virtio-mmio-block-verified-bundle/libVirtioMmioBlock.a`（我们通过 `build-fuxi-virtio-bindings.py` 把 11 个 IOBlockStorageDevice 绑定追加进去）。

---

## 5. 关键事实

### 硬件参数

| 项 | 值 |
| --- | --- |
| UFS 控制器 | `0x1d84000` / `0x3000` |
| UFS PHY | `0x1d80000` / `0x2000` |
| GCC | `0x100000` |
| apps_smmu | `0x15000000`，stream `0x60` |
| userdata | `0x2f7840..0x3afc3fa`（3110976..61880618），4096 字节块 |
| root UUID | `04769D26-2CA0-4825-B443-E2E5F88300F2` |

### boot-arg

| boot-arg | 含义 | fuxi |
| --- | --- | --- |
| `native-ufs-probe=N` | 只读/逐段验证 | 验证期临时 |
| `native-ufs-root=1` | root 路径 | **采用** |
| `native-fuxi-ufs-root=1` | old 风格 | 弃用 |

### probe 档位

| 档位 | 作用 |
| --- | --- |
| 2 | 只读寄存器 |
| 3-5,9 | adoptAndRead |
| 6 | request list |
| 7 | SMMU stream |
| 8 | context bank |
| 10 | GPT → userdata → 首块 + manifest |
| 11 | 每窗口 EFI PART |
| 12 | 完整 startRoot + media 报告 |
| 13 | 内存快照 |

---

## 6. 验证步骤

### 编译

~~~bash
cd <unixnu-fork>
export GITHUB_TOKEN=<token>
./unixnu defconfig fuxi_defconfig --device ../unixnu-fuxi   # 改 defconfig 后必须重跑
./unixnu build kernel --device ../unixnu-fuxi
~~~

### 上机（fastboot boot，不刷写）

临时副本 board.toml 加 `native-ufs-probe=10`（验 GPT 几何）或 `=12`（验全链路），重打 payload 上机。

---

## 7. 遗留 / 待确认

1. **阶段2 恢复**：VerifiedRoot + RamBlock + boot-progress（挂 APFS root）。
2. **boot-log 启用链**：`zzzc-boot-log.patch` 已补，还需 `sheng-log=1` boot-arg + `read-sheng-log.py`（读日志）。
3. **pinned .S 风险**：绑定 slide=-0x1000000 的 21H461 kernelcache，换 pin 要重审计。
4. **apps_smmu**：驱动硬编码 `0x15000000`/stream `0x60`，DT matching 需在 device 层补节点。
