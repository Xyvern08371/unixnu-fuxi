# loader/ —— M1 / M2 骨架

这是 **UEFI Application**，不是你之前设想的"整个 UEFI"。原因见 `../docs/boot-chain.md`：
在 fuxi 上真正干"固件"活的是 Renegade 那套 EDK2 UEFI，我们只需要在它的 DXE 环境里跑一个
应用，负责 **准备设备树 + 装载载荷 + ExitBootServices + 跳转**。

## 它现在做什么

1. 打开 ESP 根目录，读 `\fuxi.dtb`（由 `appledt` 生成）和 `\payload.bin`
2. 打印 `CurrentEL`、设备树/载荷的物理地址和大小
3. 若 `payload.bin` 存在：`GetMemoryMap` → `ExitBootServices` → 关中断 → `x0=DT, br payload`

没有 `payload.bin` 时只做自检然后正常退出，方便先验证链路。

## 构建（本机没有工具链，故未验证）

**推荐：走 GitHub Actions，零本地依赖。**
把这个仓库推到 GitHub，`.github/workflows/build-loader.yml` 会自动编，
产物在 Actions 的 Artifacts 里（`FuxiLoader-efi`）。

**本地构建（有工具链时）：**

```bash
git clone --depth 1 --branch edk2-stable202408 https://github.com/tianocore/edk2
cd edk2 && git submodule update --init --depth 1
source edksetup.sh                      # Windows: edksetup.bat
export PACKAGES_PATH="$PWD:$PWD/.."     # 让 edk2 找到 ios-on-fuxi/loader
build -p ../loader/FuxiLoader.dsc -a AARCH64 -t GCC5 -b RELEASE
```

需要 aarch64 交叉工具链（`aarch64-linux-gnu-` 或 LLVM 的 `clang --target=aarch64`），
以及 edk2 的 `BaseTools`。

产物：`Build/FuxiLoader/RELEASE_GCC5/AARCH64/FuxiLoader.efi`，丢到 ESP 根目录，
在 UEFI Shell 里执行 `FuxiLoader.efi`。

## 已知问题 / 下一步

- [ ] **未编译验证**：本机无 clang/gcc/make，代码按 EDK2 接口书写，首次编译大概率要修几个头文件引用
- [ ] `JumpToPayload` 只处理平坦二进制；ELF 装载（解析 PT_LOAD、清 bss、给内核换栈）是 M2 的活
- [ ] 交接时 MMU / cache 状态需要和载荷约定：XNU 的 arm64 入口有自己的页表建立流程，但入口
      前的 `SCTLR_EL1` 状态必须先确认（这是最容易"跳过去就静默重启"的地方）
- [ ] 需要在一台机器上先验证 `CurrentEL`：Renegade UEFI 在骁龙上通常把我们的应用放在 EL2，
      而 XNU 期望 EL1 —— 若是 EL2，跳转前必须自己 `eret` 降级
