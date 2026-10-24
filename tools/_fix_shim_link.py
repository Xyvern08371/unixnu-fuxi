"""给 shim 链接命令补上 ufs.o。"""

import io

P = r"E:\ios-on-fuxi\loader-shim-fuxi\build-shim.sh"
t = io.open(P, encoding="utf-8").read()

needle = "$OUT/loader.o \\"
if "$OUT/ufs.o" in t:
    print("已经有 ufs.o 了")
else:
    assert needle in t, "link line not found"
    t = t.replace(needle, "$OUT/loader.o $OUT/ufs.o \\", 1)
    io.open(P, "w", encoding="utf-8", newline="\n").write(t)
    print("已补上 ufs.o")

for i, line in enumerate(io.open(P, encoding="utf-8").read().split("\n"), 1):
    if "start.o" in line or "ufs.o" in line:
        print("  L%d: %s" % (i, line))
