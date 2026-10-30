"""shim: 内核窗口覆盖帧缓冲 0xB8000000，并把重叠检查改成只看"实际写入区间"。

原因：panic far=0xFFFFFE000B3D0008 → 物理 0xB3D0008，落在帧缓冲里，
但窗口只到 0xA7000000，physmap 没映射到帧缓冲 → 数据中止。

窗口放大到 0xC0000000 后，帧缓冲（0xB8000000）就在窗口内。
而内核真正写入的只有 [phys_base, top]（约 33MB），不会碰到 shim 自己（0xA8080000），
所以重叠检查要按写入区间算，而不是整个窗口。
"""

import io

L = r"E:\ios-on-fuxi\loader-shim-fuxi\loader.c"
t = io.open(L, encoding="utf-8").read()

t = t.replace(
    "const uint64_t FUXI_LOW_SIZE = 0x17000000ULL;   /* 到 0xA7000000，避开 shim 自身(约 0xA8080000) */",
    "const uint64_t FUXI_LOW_SIZE = 0x30000000ULL;   /* 到 0xC0000000，把帧缓冲 0xB8000000 包进 physmap */",
)

old_check = "if (src_end > phys_base && src < phys_base + mem_size)"
new_check = "/* 只检查内核真正写入的区间（phys_base..top），窗口可以比它大 */"

if old_check in t:
    # 先把检查挪到算完 top 之后
    t = t.replace("""	if (src_end > phys_base && src < phys_base + mem_size)
		return "payload overlaps kernel memory";
""", "")
    anchor = """	uintptr_t top = ba_pa + PAGE_16K;"""
    assert anchor in t
    t = t.replace(anchor, anchor + """

	/* payload 必须落在内核写入区间之外（它会边拷边被读） */
	if (src_end > phys_base && src < top)
		return "payload overlaps kernel memory";""", 1)
    print("loader.c: 窗口 0x30000000，重叠检查改成 phys_base..top")

io.open(L, "w", encoding="utf-8", newline="\n").write(t)

for i, line in enumerate(io.open(L, encoding="utf-8").read().split("\n"), 1):
    if "FUXI_LOW_SIZE" in line or "payload overlaps" in line or "src < top" in line:
        print("  L%d: %s" % (i, line.strip()))
