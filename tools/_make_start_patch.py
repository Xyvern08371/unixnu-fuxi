import io

# 生成补丁：在 _start 入口写一个像素到帧缓冲（证明内核代码被执行）
# 上下文必须和 xnu-8796 的 start.s 一致（约 L220-224）

path = r"E:\ios-on-fuxi\xnu\patches\0019-fuxi-start-pixel-mark.patch"

lines = []
lines.append("diff --git a/osfmk/arm64/start.s b/osfmk/arm64/start.s")
lines.append("--- a/osfmk/arm64/start.s")
lines.append("+++ b/osfmk/arm64/start.s")
lines.append("@@ -219,6 +219,12 @@")
lines.append("  */")
lines.append(" \t.align\t3")
lines.append(" \t.globl EXT(_start)")
lines.append(" LEXT(_start)")
lines.append("+\t/*")
lines.append("+\t * fuxi: 证明内核代码真的被执行——往帧缓冲左上角写一个绿色像素。")
lines.append("+\t * 这里 MMU 还没开，x0 = boot_args（不能动），用 x9/x10。")
lines.append("+\t */")
lines.append("+\tMOV64\tx9, 0xB0000000")
lines.append("+\tMOV64\tx10, 0x0000FF00")
lines.append("+\tstr\tw10, [x9]")
lines.append(" \tb\tEXT(start_first_cpu)")
lines.append(" ")
lines.append(" ")

io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
print(f"已生成 {path}")
print("检查 tab 是否保留:")
for l in lines[:12]:
    print("  " + l.replace("\t", "<TAB>")[:100])

# 本地模拟：把补丁应用到下载的 start.s 上，验证上下文能匹配
src = io.open(r"E:\download\start-8796.s", encoding="utf-8").read().split("\n")
# 找 LEXT(_start)
idx = next(i for i, l in enumerate(src) if l.strip() == "LEXT(_start)")
print("\n下载文件里 _start 在第", idx + 1, "行")
print("上下文检查:")
for k in range(idx - 3, idx + 3):
    print("  %4d| %s" % (k + 1, src[k].replace("\t", "<TAB>")[:60]))
