"""shim: 内核物理基址从 4GB 改到低区 0x90000000。

fuxi 上访问 0x1_0100_4000 触发同步外部中止（ESR 0x96000010 / FAR 0x101004000），
说明 4GB 以上的 DRAM 当前不可访问。改成低区并在拷贝后同时修正 ADT 里的
dram-base/dram-size，保证 XNU 看到的物理内存窗口和 boot_args 一致。
"""

import io

L = r"E:\ios-on-fuxi\loader-shim-fuxi\loader.c"
t = io.open(L, encoding="utf-8").read()

if "FUXI_LOW_PHYS" in t:
    print("已经改过了")
else:
    # 1) 在 loader_boot 开头加常量覆盖
    anchor = "\tuint64_t pa_of_va_base = p->phys_base - p->virt_base;\t/* pa = va + this */"
    assert anchor in t, "pa_of_va_base 没找到"
    new = """	/*
	 * FUXI_LOW_PHYS：4GB 以上的地址在这台机器上访问会触发同步外部中止
	 * （ESR 0x96000010 / FAR 0x101004000），所以内核放到低区。
	 */
	const uint64_t FUXI_LOW_PHYS = 0x90000000ULL;
	const uint64_t FUXI_LOW_SIZE = 0x70000000ULL;
	uint64_t phys_base = FUXI_LOW_PHYS;
	uint64_t mem_size  = FUXI_LOW_SIZE;

	uint64_t pa_of_va_base = phys_base - p->virt_base;	/* pa = va + this */"""
    t = t.replace(anchor, new, 1)

    # 2) con_hex2 PHYS 用新值
    t = t.replace('con_hex2("PHYS", "base=", p->phys_base, "size=", p->mem_size);',
                  'con_hex2("PHYS", "base=", phys_base, "size=", mem_size);')

    # 3) boot_args 用新值
    t = t.replace("\tba->physBase = p->phys_base;", "\tba->physBase = phys_base;")
    t = t.replace("\tba->memSize = p->mem_size;", "\tba->memSize = mem_size;")
    t = t.replace("\tba->memSizeActual = p->mem_size;", "\tba->memSizeActual = mem_size;")

    # 4) 拷贝完 ADT 后，把里面的 dram-base/dram-size 也换掉
    old_copy = "\tcopy64(adt_pa, src + p->adt_off, p->adt_size);"
    assert old_copy in t
    new_copy = """	copy64(adt_pa, src + p->adt_off, p->adt_size);

	/* ADT 里的 dram-base/dram-size 也要跟着改（XNU 用它建 physmap） */
	{
		volatile uint64_t *w = (volatile uint64_t *)adt_pa;
		uint64_t n = p->adt_size / 8;
		for (uint64_t i = 0; i < n; i++) {
			if (w[i] == p->phys_base)
				w[i] = phys_base;
			else if (w[i] == p->mem_size)
				w[i] = mem_size;
		}
	}"""
    t = t.replace(old_copy, new_copy, 1)

    # 5) 重叠检查用新窗口
    t = t.replace("if (src_end > p->phys_base && src < p->phys_base + p->mem_size)",
                  "if (src_end > phys_base && src < phys_base + mem_size)")

    io.open(L, "w", encoding="utf-8", newline="\n").write(t)
    print("loader.c: 内核物理基址 -> 0x90000000，并同步修正 ADT")

for i, line in enumerate(io.open(L, encoding="utf-8").read().split("\n"), 1):
    if any(k in line for k in ("FUXI_LOW_PHYS", "FUXI_LOW_SIZE", "phys_base = ", "ba->physBase")):
        print("  L%d: %s" % (i, line.strip()))
