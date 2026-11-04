"""修 shim 的 payload 偏移：按 _payload_start 符号补齐，而不是按段大小。

原因：链接脚本里 . += 0x8000 / _sec_stacks 这些预留不产生 section，
按段表算出来的大小（0x1C000）比 _payload_start（0x2C000）小，
导致 payload 被追加到错误偏移，shim 读不到 magic。
"""

import io

B = r"E:\ios-on-fuxi\loader-shim-fuxi\build-shim.sh"
t = io.open(B, encoding="utf-8").read()

# 用 _payload_start 符号作为补齐目标
old_calc = t[t.find("# 用 ELF 段表算镜像总大小"):t.find('ls -l "$OUT/Image"')]
new_calc = '''# 用链接脚本里的 _payload_start 决定 payload 起始偏移
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
  printf '%08x' "$TOTAL" | sed 's/\\(..\\)\\(..\\)\\(..\\)\\(..\\)/\\4\\3\\2\\1/' | xxd -r -p | \\
    dd of="$OUT/Image" bs=1 seek=16 conv=notrunc status=none
  echo "  image_size 字段 -> $TOTAL"
fi

'''
t = t.replace(old_calc, new_calc, 1)
io.open(B, "w", encoding="utf-8", newline="\n").write(t)
print("build-shim.sh: 改成按 _payload_start 补齐")
print()
print(t[t.find("# 用链接脚本里"):t.find('echo "=== shim 编译完成 ===')])
