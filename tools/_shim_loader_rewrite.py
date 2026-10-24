"""重写 loader.c 的 loader_boot：支持「内嵌 payload」和「ramdisk payload」两种来源。"""

import io

L = r"E:\ios-on-fuxi\loader-shim-fuxi\loader.c"
t = io.open(L, encoding="utf-8").read()

idx = t.find("const char *loader_boot(uintptr_t dtb)")
assert idx > 0, "loader_boot not found"

new_fn = r'''const char *loader_boot(uintptr_t dtb)
{
	const struct payload *p;
	uintptr_t src;		/* payload 起始物理地址 */
	uintptr_t src_end;	/* 重叠检查用 */

	if (g_payload_ptr != 0) {
		/* fuxi: payload 内嵌在镜像末尾（ABL 的 ramdisk 不可用） */
		src = (uintptr_t)g_payload_ptr;
		src_end = src + PAGE_16K;	/* 保守估计，够做重叠检查 */
		con_hex("EMBED", src);
	} else {
		uint64_t rd_start, rd_end;

		if (!fdt_chosen_u64(dtb, "linux,initrd-start", &rd_start) ||
		    !fdt_chosen_u64(dtb, "linux,initrd-end", &rd_end))
			return "no initrd in /chosen";
		con_hex2("INITRD", "lo=", rd_start, "hi=", rd_end);
		src = (uintptr_t)rd_start;
		src_end = (uintptr_t)rd_end;
	}

	p = (const struct payload *)src;
	if (!magic_ok(p->magic))
		return "bad payload magic";
	if (p->version != 1 || (p->adt_off & 7) || (src & 7))
		return "bad payload header";

	uint64_t pa_of_va_base = p->phys_base - p->virt_base;	/* pa = va + this */
	con_hex2("PHYS", "base=", p->phys_base, "size=", p->mem_size);
	con_hex("VIRT", p->virt_base);
	con_hex("ENTRY", p->entry_va);

	/* 目标内核区域不能和 payload 自己重叠 */
	if (src_end > p->phys_base && src < p->phys_base + p->mem_size)
		return "payload overlaps kernel memory";

	for (uint32_t i = 0; i < p->nsegs; i++) {
		const struct payload_seg *s = &p->segs[i];
		uintptr_t dst = s->vmaddr + pa_of_va_base;
		copy64(dst, src + s->file_off, s->file_size);
		if (s->vmsize > s->file_size)
			zero64(dst + ((s->file_size + 7) & ~7UL), s->vmsize - ((s->file_size + 7) & ~7UL));
	}
	con_hex2("SEGS", "n=", p->nsegs, "end=", p->kernel_end + pa_of_va_base);

	uintptr_t adt_pa = p->kernel_end + pa_of_va_base;
	copy64(adt_pa, src + p->adt_off, p->adt_size);
	uintptr_t ba_pa = (adt_pa + p->adt_size + PAGE_16K - 1) & ~(PAGE_16K - 1);
	uintptr_t top = ba_pa + PAGE_16K;

	zero64(ba_pa, PAGE_16K);
	volatile struct boot_args *ba = (volatile struct boot_args *)ba_pa;
	ba->Revision = 2;
	ba->Version = 2;
	ba->virtBase = p->virt_base;
	ba->physBase = p->phys_base;
	ba->memSize = p->mem_size;
	ba->topOfKernelData = top;
	ba->Video.v_baseAddr = FB_BASE;
	ba->Video.v_display = 1;
	ba->Video.v_rowBytes = FB_STRIDE;
	ba->Video.v_width = FB_W;
	ba->Video.v_height = FB_H;
	ba->Video.v_depth = 32;
	ba->deviceTreeP = adt_pa - pa_of_va_base;
	ba->deviceTreeLength = (uint32_t)p->adt_size;
	for (int i = 0; i < BOOT_LINE_LENGTH; i++)
		ba->CommandLine[i] = p->cmdline[i];
	ba->memSizeActual = p->mem_size;
	con_hex2("BOOTARG", "pa=", ba_pa, "top=", top);

	uintptr_t entry_pa = p->entry_va + pa_of_va_base;
	con_hex("JUMP", entry_pa);
	con_str("XNU", "jumping (fbcon clears screen)");

	__asm__ volatile("dsb sy; ic iallu; dsb sy; isb" ::: "memory");
	((xnu_entry_t)entry_pa)(ba_pa);
	return "xnu returned";
}
'''

t = t[:idx] + new_fn
io.open(L, "w", encoding="utf-8", newline="\n").write(t)
print("loader.c: loader_boot 已重写（支持内嵌/ramdisk 两种）")

for i, line in enumerate(io.open(L, encoding="utf-8").read().split("\n"), 1):
    if "g_payload_ptr" in line or "EMBED" in line:
        print("  L%d: %s" % (i, line.strip()))
