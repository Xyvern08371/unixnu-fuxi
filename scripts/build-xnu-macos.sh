#!/bin/bash
# 在 macOS 上原生构建 open-source XNU（arm64）
#
# 用法:
#   ./scripts/build-xnu-macos.sh              # 默认 xnu-8792.81.2
#   XNU_TAG=xnu-10002.1.13 ./scripts/build-xnu-macos.sh
#
# 需要: Xcode 或 Command Line Tools（xcode-select --install）
# 产物: ./xnu/BUILD/obj/RELEASE_ARM64/

set -euo pipefail

XNU_TAG="${XNU_TAG:-xnu-8792.81.2}"
WORK="$(cd "$(dirname "$0")/.." && pwd)"
cd "$WORK"

echo "=== 环境 ==="
sw_vers
xcode-select -p
clang --version | head -2
echo "CPU: $(sysctl -n hw.ncpu)"

if ! command -v make >/dev/null 2>&1; then
    echo "缺少 make（安装 Xcode Command Line Tools: xcode-select --install）"
    exit 1
fi

# Xcode 15+ 的 SDK 删了 availability.pl，xnu 会因此失败；这里是兜底
SDK="$(xcrun --sdk macosx --show-sdk-path 2>/dev/null || true)"
if [ -n "$SDK" ]; then
    AVA="$SDK/usr/local/libexec/availability.pl"
    if [ ! -x "$AVA" ]; then
        echo "=== 缺少 availability.pl，造最小替身 ==="
        sudo mkdir -p "$(dirname "$AVA")"
        printf '#!/usr/bin/env perl\nexit 0;\n' | sudo tee "$AVA" >/dev/null
        sudo chmod +x "$AVA"
    fi
    echo "availability.pl: $AVA"
fi
if [ ! -d xnu ]; then
    echo "=== 克隆 XNU $XNU_TAG ==="
    git clone --depth 1 --branch "$XNU_TAG" \
        https://github.com/apple-oss-distributions/xnu.git
fi

cd xnu
echo "=== 当前提交 ==="
git log --oneline -1

echo "=== 开始构建（arm64 RELEASE）==="
make -j"$(sysctl -n hw.ncpu)" ARCH_CONFIGS=ARM64 KERNEL_CONFIGS=RELEASE 2>&1 | tee ../xnu-build.log

echo
echo "=== 产出物 ==="
find BUILD -maxdepth 4 -type f \( -name "kernel*" -o -name "mach*" \) 2>/dev/null | head -30
ls -lh BUILD/obj/RELEASE_ARM64/ 2>/dev/null || true

echo
echo "完成。日志: $WORK/xnu-build.log"
echo "下一步（给引导器用）需要把 Mach-O 内核转成可跳转的镜像，这一步还没做。"
