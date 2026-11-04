"""shim: 跳转前打印入口字节和 SCTLR，确认段拷贝/MMU 状态。"""

import io

L = r"E:\ios-on-fuxi\loader-shim-fuxi\loader.c"
t = io.open(L, encoding="utf-8").read()

if "CODE@ENTRY" in t:
    print("已经加过")
else:
    anchor = """	uintptr_t entry_pa = p->entry_va + pa_of_va_base;
	con_hex("JUMP", entry_pa);"""
    assert anchor in t, "JUMP 锚点没找到"
    new = """	uintptr_t entry_pa = p->entry_va + pa_of_va_base;
	con_hex("JUMP", entry_pa);

	/* 跳转前确认：入口处真的是代码吗？MMU 真的是关的吗？ */
	{
		volatile const uint64_t *e = (volatile const uint64_t *)entry_pa;
		uint64_t sctlr;

		con_hex("CODE@ENTRY", e[0]);
		con_hex("CODE@+8", e[1]);

		__asm__ volatile("mrs %0, sctlr_el1" : "=r"(sctlr));
		con_hex("SCTLR", sctlr);
	}"""
    t = t.replace(anchor, new, 1)
    io.open(L, "w", encoding="utf-8", newline="\n").write(t)
    print("loader.c: 已加 CODE@ENTRY / SCTLR 诊断")

for i, line in enumerate(io.open(L, encoding="utf-8").read().split("\n"), 1):
    if "CODE@ENTRY" in line or "SCTLR" in line:
        print("  L%d: %s" % (i, line.strip()))
