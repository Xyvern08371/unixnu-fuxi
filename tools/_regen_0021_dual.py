"""重新生成 0021（停机实验）：在 _start 处画两块色，然后 wfi 停机。

- 0xB8000000 绿：裸机阶段 splash 帧缓冲（应该可见）
- 0xB0000000 黄绿：UEFI GOP 的地址（对比用）
"""

import io

PATH = r"E:\ios-on-fuxi\xnu\patches\0021-fuxi-early-stage-marks.patch"
ROWS = 256


def fill(addr_hex, color_hex, comment):
    out = [
        "+\t/* " + comment + " */",
        "+\tMOV64\tx9, " + addr_hex,
        "+\tMOV64\tx10, " + color_hex,
        "+\tMOV64\tx11, " + str(ROWS * 1080),
        "+\t1:",
        "+\tstr\tw10, [x9], #4",
        "+\t\tsubs\tx11, x11, #1",
        "+\t\tb.ne\t1b",
        "+\tdsb\tsy",
    ]
    return out


added = (
    [
        "+",
        "+\t/* fuxi 停机实验：刷色块后 wfi，看到颜色即内核已执行 */",
    ]
    + fill("0xB8000000", "0x0000FF00", "裸机可见的 splash 帧缓冲（绿）")
    + fill("0xB0000000", "0x00FFFF00", "UEFI GOP 的地址（黄绿，对比用）")
    + [
        "+\t2:",
        "+\twfi",
        "+\tb\t2b",
    ]
)

before = ["\t.align\t3", "\t.globl EXT(_start)", "LEXT(_start)"]
after = ["\tb\tEXT(start_first_cpu)"]

body = [" " + c for c in before] + added + [" " + c for c in after]
old = sum(1 for l in body if l[:1] in " -")
new = sum(1 for l in body if l[:1] in " +")

out = [
    "diff --git a/osfmk/arm64/start.s b/osfmk/arm64/start.s",
    "--- a/osfmk/arm64/start.s",
    "+++ b/osfmk/arm64/start.s",
    "@@ -220,%d +220,%d @@" % (old, new),
] + body

io.open(PATH, "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
print("已重新生成 0021，hunk:", out[3])
