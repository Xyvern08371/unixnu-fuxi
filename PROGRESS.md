# fuxi 进度同步（2026-11-04）

## 已解决：boot 到 SpringBoard 的根因 = unique-chip-id 不匹配

协作者内核的 ADT 里 `unique-chip-id = 0x5be4ac1565101544`（他的芯片），
本机实际是 `0xce854c9ae043320b`（笔记 §4）。

- 现象：菜单选 `fuxi first boot` → XNU 早期崩溃 → 退回菜单。
- 修复：只改 ADT 里 8 字节 chip-id，重封 v1 镜像。
- 可用镜像：`boot-t36-v1-ourchip.img`（sha256 `3e2bfb65307daaf7aab11eee0dff028d1cde7056e63738668dc0f565f13f704a`）。

## GPU 稳定性

`unixnu.toml` 引导参数里 `sheng-gpu-dcvs=1 → 0`（关 GPU 动态调频）后，
「时流畅时卡」明显改善。残留卡顿可能是散热降频。

## WiFi（WCN7850 / ath12k）—— 诊断与前置已就绪

### 诊断
- 当前内核（t36）**没有** ath12k/WifiProbe/WifiNet/WCN7850 符号 → WiFi 没编进内核。
- board.toml 已含 `sheng-wifi=5` + `include = [..., "Ath12kWifi", ...]`，
  构建编排在 `scripts/build-gop-legacy-display.py` → `scripts/build-ath12k-wifi.py`。

### 固件来源（不在 7GiB 整包里，是 GitHub 小文件）
- `ianchb/sheng-firmware` @ `2c1e2729a085c7f0470c855d236e49455c4601f0`：
  - `ath12k/WCN7850/hw2.0/amss.bin`（6,271,040 B，c7-00108）
  - `ath12k/WCN7850/hw2.0/board-2.bin`（113,284 B）
  - `ath12k/WCN7850/hw2.0/m3.bin`（299,660 B）
- 下载需走 gh-proxy 镜像（raw.githubusercontent.com 被墙）。

### 已补上的缺失工具
- `local-tools/make-wifi-fw.py`：把 amss.bin 打成 WFW1 容器，写入 `oops` 分区。
  （WifiProbe.cpp 启动时从 `oops` 分区读 `WFW1` 魔数容器取 amss.bin）
- `scripts/build-ath12k-wifi.py`：去掉 `brew --prefix llvm` 依赖，改 `/usr/bin`（WSL 无 brew）。

### 剩余：内核重编
- 命令：`cd /root/unixnu/UniXNU && python3 unixnu defconfig fuxi_full_defconfig -D ../UniXNU-fuxi-merged && python3 unixnu kernel -D ../UniXNU-fuxi-merged -j 8`
- 卡点：sm8550-common feed 的 `patches/xnu/native-smp-secondary.patch` 与
  基础 xnu feed（d8b80295118e）不匹配（patch does not apply）。
  该补丁要改 `MAX_CPUS 4→8` 和 `#if HAS_CLUSTER→|| defined(BCM2837)`；
  feed 引脚在 `feeds.toml`（sm8550 = `23b2049fcd9e30356161def84231334fb55ecca9`）。
