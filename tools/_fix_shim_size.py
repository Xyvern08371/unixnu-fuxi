"""修 build-shim.sh：mawk 没有 strtonum，改用 bash 算术。"""

import io

P = r"E:\ios-on-fuxi\loader-shim-fuxi\build-shim.sh"
t = io.open(P, encoding="utf-8").read()

old = 'SIZE=$($NM "$OUT/shim.elf" | awk \'$3=="_end"{print strtonum("0x"$1)}\')'
new = 'END_HEX=$($NM "$OUT/shim.elf" | awk \'$3=="_end"{print $1}\')\nSIZE=$((16#$END_HEX))'

if "strtonum" in t:
    assert old in t, "size line not found"
    t = t.replace(old, new, 1)
    io.open(P, "w", encoding="utf-8", newline="\n").write(t)
    print("build-shim.sh: 改用 bash 算术")
else:
    print("已经改过")

for i, line in enumerate(io.open(P, encoding="utf-8").read().split("\n"), 1):
    if "END_HEX" in line or "SIZE=$" in line or "truncate" in line:
        print("  L%d: %s" % (i, line))
