"""重写 0021：在 start_first_cpu 入口画品红色块后直接停机（决定性实验）。"""

import io

path = r"E:\ios-on-fuxi\xnu\patches\0021-fuxi-early-stage-marks.patch"
STRIDE = 4320


def marker(y, color, rows):
    off = y * STRIDE
    return [
        "+\tMOV64\tx9, 0xB0000000",
        "+\tMOV64\tx12, 0x%X" % off,
        "+\tadd\tx9, x9, x12",
        "+\tMOV64\tx10, " + color,
        "+\tMOV64\tx11, " + str(rows * 1080),
        "+\t1:",
        "+\tstr\tw10, [x9], #4",
        "+\t\tsubs\tx11, x11, #1",
        "+\t\tb.ne\t1b",
        "+\tdsb\tsy",
    ]


added = (
    [
        "+",
        "+\t/* fuxi 决定性实验：画 64 行品红色块，然后停机。 */",
        "+\t/* 看到色块 = 内核确实执行到了 start_first_cpu。 */",
    ]
    + marker(1200, "0x00FF00FF", 64)
    + [
        "+\t2:",
        "+\twfi",
        "+\tb\t2b",
    ]
)

ctx = ["LEXT(start_first_cpu)", "", "\t// Unlock the core for debugging"]
body = [" " + c for c in ctx] + added + [" "]
old = sum(1 for l in body if l[:1] in " -")
new = sum(1 for l in body if l[:1] in " +")
hdr = "@@ -457,%d +457,%d @@" % (old, new)

out = [
    "diff --git a/osfmk/arm64/start.s b/osfmk/arm64/start.s",
    "--- a/osfmk/arm64/start.s",
    "+++ b/osfmk/arm64/start.s",
    hdr,
] + body

io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
print("已重写 0021，hunk:", hdr)
