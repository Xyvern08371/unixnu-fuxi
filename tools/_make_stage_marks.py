"""生成 0021 补丁：在 start_first_cpu 里加两个早期标记（MMU 仍关闭）。"""

import io

path = r"E:\ios-on-fuxi\xnu\patches\0021-fuxi-early-stage-marks.patch"
STRIDE = 4320


def marker(y, color_hex, rows, comment):
    off = y * STRIDE
    out = ["+\t/* fuxi: " + comment + " */"]
    out.append("+\tMOV64\tx9, 0xB0000000")
    out.append("+\tMOV64\tx12, 0x%X" % off)
    out.append("+\tadd\tx9, x9, x12")
    out.append("+\tMOV64\tx10, " + color_hex)
    out.append("+\tMOV64\tx11, " + str(rows * 1080))
    out.append("+\t1:")
    out.append("+\tstr\tw10, [x9], #4")
    out.append("+\t\tsubs\tx11, x11, #1")
    out.append("+\t\tb.ne\t1b")
    out.append("+\tdsy_placeholder")
    # 上面一行占位替换成 dsb sy（避免转义问题）
    out[-1] = "+\tdsb\tsy"
    return out


def hunk(old_start, ctx_before, added_lines, ctx_after):
    body = [" " + c for c in ctx_before] + added_lines + [" " + c for c in ctx_after]
    old = sum(1 for l in body if l[:1] in " -")
    new = sum(1 for l in body if l[:1] in " +")
    hdr = "@@ -%d,%d +%d,%d @@" % (old_start, old, old_start, new)
    return [hdr] + body


h1 = hunk(459,
          ["\t// Unlock the core for debugging",
           "\tmsr\t\tOSLAR_EL1, xzr",
           "\tmsr\t\tDAIFSet, #(DAIFSC_ALL)\t\t\t\t// Disable all interrupts"],
          marker(500, "0x0000FFFF", 8, "进入 start_first_cpu"),
          ["", "\tmov\t\tx20, x0"])

h2 = hunk(344,
          ["\t// Convert lr to KVA",
           "\tadd\t\tlr, lr, x22",
           "\tsub\t\tlr, lr, x23"],
          marker(560, "0x00FF00FF", 8, "页表建完，即将进 common_start"),
          ["", "\tb\t\tcommon_start"])

# 按原始行号升序排列（344 在前，459 在后）
lines = [
    "diff --git a/osfmk/arm64/start.s b/osfmk/arm64/start.s",
    "--- a/osfmk/arm64/start.s",
    "+++ b/osfmk/arm64/start.s",
] + h2 + h1

io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
print("已生成补丁，hunk 顺序:", h2[0], "然后", h1[0])
print("行数:", len(lines))

# 用下载的 start.s 验证上下文能匹配
src = io.open(r"E:\download\start-8796.s", encoding="utf-8").read().split("\n")
def check(ctx, start_hint):
    for i in range(max(0, start_hint - 30), min(len(src), start_hint + 30)):
        if src[i].rstrip() == ctx[0].rstrip() and \
           all(src[i + k].rstrip() == ctx[k].rstrip() for k in range(len(ctx)) if i + k < len(src)):
            return i + 1
    return None

print("hunk2 上下文匹配行:", check([c for c in h2[1:] if c[:1] == ' '][:3], 344))
print("hunk1 上下文匹配行:", check([c for c in h1[1:] if c[:1] == ' '][:3], 459))
