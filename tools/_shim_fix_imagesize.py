"""修两个可疑点：
1) gzip 用 -n（不写文件名/时间戳，和 UEFI 镜像一致）
2) Image 头的 image_size 字段改成实际大小（含内嵌 payload）
"""

import io

# 1) build-shim.sh: 内嵌 payload 后修正 image_size
B = r"E:\ios-on-fuxi\loader-shim-fuxi\build-shim.sh"
b = io.open(B, encoding="utf-8").read()

if "image_size" not in b:
    old = '''if [ -n "${PAYLOAD_FILE:-}" ]; then
  echo "=== 内嵌 payload ==="
  cat "$PAYLOAD_FILE" >> "$OUT/Image"
fi'''
    new = '''if [ -n "${PAYLOAD_FILE:-}" ]; then
  echo "=== 内嵌 payload ==="
  cat "$PAYLOAD_FILE" >> "$OUT/Image"

  # ARM64 Image 头里的 image_size（偏移 0x10）改成实际总大小：
  # ABL 可能用它做校验/决定复制多少字节。
  TOTAL=$(stat -c%s "$OUT/Image")
  printf '%08x' "$TOTAL" | sed 's/\\(..\\)\\(..\\)\\(..\\)\\(..\\)/\\4\\3\\2\\1/' | xxd -r -p | \\
    dd of="$OUT/Image" bs=1 seek=16 conv=notrunc status=none
  echo "  image_size 字段 -> $TOTAL"
fi'''
    assert old in b, "payload block not found"
    b = b.replace(old, new, 1)
    io.open(B, "w", encoding="utf-8", newline="\n").write(b)
    print("build-shim.sh: 已加 image_size 修正")

# 2) workflow: gzip -n
W = r"E:\ios-on-fuxi\.github\workflows\build-fuxi-shim.yml"
w = io.open(W, encoding="utf-8").read()
if "gzip -9 -n" not in w:
    w = w.replace("gzip -9 -c loader-shim-fuxi/out-shim/Image",
                  "gzip -9 -n -c loader-shim-fuxi/out-shim/Image")
    io.open(W, "w", encoding="utf-8", newline="\n").write(w)
    print("workflow: gzip -n（不写文件名）")

for i, line in enumerate(io.open(B, encoding="utf-8").read().split("\n"), 1):
    if "image_size" in line or "TOTAL" in line or "xxd" in line:
        print("  build-shim L%d: %s" % (i, line.rstrip()))
