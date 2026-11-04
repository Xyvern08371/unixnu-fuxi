#!/bin/bash
# 编译 fuxi shim 并打包成可 fastboot flash 的 boot.img
#
# 环境：Linux + aarch64-linux-gnu-gcc（GitHub ubuntu runner 自带或 apt 装）
set -euo pipefail

cd "$(dirname "$0")"

CC=${CC:-aarch64-linux-gnu-gcc}
OBJCOPY=${OBJCOPY:-aarch64-linux-gnu-objcopy}

CFLAGS="-O2 -ffreestanding -nostdlib -fno-pic -mgeneral-regs-only -mstrict-align -fno-stack-protector -Wall -Wextra"

OUT=out-shim
rm -rf "$OUT"
mkdir -p "$OUT"

SRCS="start.S shim.c console.c mmu.c fdt.c memmap.c loader.c ufs.c"

echo "=== 编译 ==="
for f in $SRCS; do
  $CC $CFLAGS -c "$f" -o "$OUT/${f%.*}.o"
  echo "  ${f%.*}.o"
done

echo "=== 链接 ==="
$CC $CFLAGS -static -T shim.ld -Wl,--build-id=none -Wl,--no-warn-rwx-segments -Wl,-N \
    "$OUT/start.o" "$OUT/shim.o" "$OUT/console.o" "$OUT/mmu.o" "$OUT/fdt.o" "$OUT/memmap.o" "$OUT/loader.o" "$OUT/ufs.o" \
    -o "$OUT/shim.elf"

$OBJCOPY -O binary "$OUT/shim.elf" "$OUT/Image"

# 用链接脚本里的 _payload_start 决定 payload 起始偏移
# （段表只覆盖真实 section，漏掉 . += 预留的栈空间）
PAYLOAD_OFF=$(aarch64-linux-gnu-nm "$OUT/shim.elf" | awk '$3=="_payload_start"{print $1}')
if [ -z "$PAYLOAD_OFF" ]; then
  echo "错误：找不到 _payload_start 符号" >&2
  exit 1
fi
PAYLOAD_OFF=$((16#$PAYLOAD_OFF))
echo "  payload 起始偏移 = $PAYLOAD_OFF"

truncate -s "$PAYLOAD_OFF" "$OUT/Image"

if [ -n "${PAYLOAD_FILE:-}" ]; then
  echo "=== 内嵌 payload ==="
  cat "$PAYLOAD_FILE" >> "$OUT/Image"

  # ARM64 Image 头里的 image_size（偏移 0x10）改成实际总大小
  TOTAL=$(stat -c%s "$OUT/Image")
  printf '%08x' "$TOTAL" | sed 's/\(..\)\(..\)\(..\)\(..\)/\4\3\2\1/' | xxd -r -p | \
    dd of="$OUT/Image" bs=1 seek=16 conv=notrunc status=none
  echo "  image_size 字段 -> $TOTAL"
fi

ls -l "$OUT/Image"

echo "=== shim 编译完成 ==="
