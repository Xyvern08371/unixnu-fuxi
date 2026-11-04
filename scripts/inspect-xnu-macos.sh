#!/bin/bash
# 检查 macOS 上构建出来的 XNU 内核镜像，输出引导器所需的全部信息。
#
# 用法: ./scripts/inspect-xnu-macos.sh [kernel 文件]
# 默认自动在 xnu/BUILD 下查找 kernel.release / kernel

set -uo pipefail

WORK="$(cd "$(dirname "$0")/.." && pwd)"
cd "$WORK"

K="${1:-}"
if [ -z "$K" ]; then
    K=$(find xnu/BUILD -type f -name "kernel.release*" 2>/dev/null | head -1)
fi
if [ -z "$K" ] || [ ! -f "$K" ]; then
    K=$(find xnu/BUILD -type f -name "kernel" 2>/dev/null | head -1)
fi
if [ -z "$K" ] || [ ! -f "$K" ]; then
    echo "找不到内核文件。先跑 ./scripts/build-xnu-macos.sh"
    echo "以下是 BUILD 目录里现有的东西："
    find xnu/BUILD -maxdepth 4 -type f 2>/dev/null | head -40
    exit 1
fi

echo "############ 基本信息 ############"
echo "文件: $K"
ls -lh "$K"
file "$K"

echo
echo "############ Mach-O 头 ############"
otool -hv "$K"

echo
echo "############ 段布局（关键：vmaddr / fileoff / filesize） ############"
otool -l "$K" | awk '
  /^  sectname|cmd LC_SEGMENT_64/ { }
  /segname/ {seg=$2; getline; vmaddr=$2; getline; vmsize=$2; getline; fileoff=$2; getline; filesize=$2; printf "seg=%-16s vmaddr=%s vmsize=%s fileoff=%s filesize=%s\n", seg, vmaddr, vmsize, fileoff, filesize}
'

echo
echo "############ 入口点 ############"
echo "--- LC_MAIN / LC_UNIXTHREAD 附近 ---"
otool -l "$K" | grep -A6 -E "LC_MAIN|LC_UNIXTHREAD" | head -40
echo "--- _start 符号 ---"
nm -n "$K" 2>/dev/null | grep -i -E " T _start$| T _start\b" | head -5
echo "--- 前 10 个符号（按地址） ---"
nm -n "$K" 2>/dev/null | head -10

echo
echo "############ 构建版本信息 ############"
vtool -show-build "$K" 2>/dev/null || echo "(vtool 不可用)"

echo
echo "############ 是否还有未压缩内核 ############"
ls -lh xnu/BUILD/obj/RELEASE_ARM64/ 2>/dev/null | head -20

echo
echo "############ 结束 ############"
echo "把上面全部输出复制给我即可。"
