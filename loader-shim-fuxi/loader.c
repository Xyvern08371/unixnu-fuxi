/*
 * Milestone 4: act as iBoot for xnu.
 *
 * mkpayload.py already resolved the kernel's chained fixups and built the
 * ADT, so this only has to: find the payload in the ABL ramdisk, copy the
 * segments to phys_base + (vmaddr - virt_base), place the ADT and
 * boot_args behind the kernel, and jump to the entry point with the MMU
 * and caches off, x0 = boot_args (physical).
 */
#include <stdint.h>
#include "console.h"
#include "fdt.h"
#include "loader.h"

#define BOOT_LINE_LENGTH	608
#define PAGE_16K		0x4000UL

extern char _head[], _end[];		/* start.S 里的镜像边界（mmu.c 也用） */

struct payload_seg {
	uint64_t vmaddr, vmsize, file_off, file_size;
};

struct payload {
	char magic[8];
	uint32_t version, nsegs;
	uint64_t virt_base, entry_va, adt_off, adt_size, kernel_end;
	uint64_t phys_base, mem_size;
	char cmdline[BOOT_LINE_LENGTH];
	struct payload_seg segs[];
};

/* pexpert/pexpert/arm64/boot.h, Revision/Version 2 */
struct boot_video {
	uint64_t v_baseAddr, v_display, v_rowBytes, v_width, v_height, v_depth;
};

struct boot_args {
	uint16_t Revision, Version;
	uint64_t virtBase, physBase, memSize, topOfKernelData;
	struct boot_video Video;
	uint32_t machineType;
	uint64_t deviceTreeP;
	uint32_t deviceTreeLength;
	char CommandLine[BOOT_LINE_LENGTH];
	uint64_t bootFlags, memSizeActual;
};

_Static_assert(__builtin_offsetof(struct payload, segs) == 0x2a8, "payload header layout");
_Static_assert(__builtin_offsetof(struct boot_args, Video) == 40, "boot_args layout");
_Static_assert(__builtin_offsetof(struct boot_args, CommandLine) == 108, "boot_args layout");
_Static_assert(sizeof(struct boot_args) == 736, "boot_args layout");

/* MMU off: everything is Device memory, so copy in aligned 8-byte words. */
static void copy64(uintptr_t dst, uintptr_t src, uint64_t n)
{
	volatile uint64_t *d = (volatile uint64_t *)dst;
	volatile const uint64_t *s = (volatile const uint64_t *)src;
	for (uint64_t i = 0; i < (n + 7) / 8; i++)
		d[i] = s[i];
}

/*
 * dc civac over [start, end)：清并无效化整段 D-cache。
 * 关 MMU/缓存前必须做，否则 XNU 关缓存后读到的是主存里的旧数据。
 */
static void dc_civac_range(uintptr_t start, uintptr_t end)
{
	uint64_t ctr;
	uint64_t line;

	__asm__ volatile("mrs %0, ctr_el0" : "=r"(ctr));
	line = 4UL << ((ctr >> 16) & 0xf);
	for (uintptr_t a = start & ~(line - 1); a < end; a += line)
		__asm__ volatile("dc civac, %0" : : "r"(a) : "memory");
	__asm__ volatile("dsb sy" ::: "memory");
}

static void zero64(uintptr_t dst, uint64_t n)
{
	volatile uint64_t *d = (volatile uint64_t *)dst;
	for (uint64_t i = 0; i < n / 8; i++)
		d[i] = 0;
}

static int magic_ok(const char *m)
{
	static const char want[] = "FUXIXNU";
	for (int i = 0; i < 8; i++)
		if (m[i] != want[i])
			return 0;
	return 1;
}

typedef void (*xnu_entry_t)(uint64_t boot_args_pa);

extern const void *g_payload_ptr;

const char *loader_boot(uintptr_t dtb)
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

	/*
	 * 窗口选择照 UniXNU DarwinBoot 的 AllocateWindow：从 ABL 的 memory map
	 * 里找最大的连续可用段，而不是写死 phys_base。真机上 4GB 内的 RAM 被
	 * Gunyah 切成多段，写死的 0x90000000+64MB 会越过实际可用区间，
	 * XNU 建 physmap 时就会踩到未映射地址。
	 */
	uint64_t phys_base = p->phys_base;
	uint64_t mem_size  = p->mem_size;

	{
		uint64_t need = (p->kernel_end - p->virt_base) + p->adt_size + 3 * PAGE_16K;
		uint64_t pick_base = 0, pick_size = 0;
		uint64_t avoid_lo = src;
		uint64_t avoid_hi = src + p->adt_off + p->adt_size;

		if (shim_pick_window(dtb, need, p->virt_base, avoid_lo, avoid_hi,
		    &pick_base, &pick_size)) {
			phys_base = pick_base;
			{
				uint64_t to_4g = 0x100000000ULL - phys_base - 0x200000ULL;
				mem_size = (pick_size > to_4g) ? pick_size : to_4g;
			}
			con_hex2("MEMWIN", "dyn base=", phys_base, "size=", mem_size);
		} else {
			con_hex2("MEMWIN", "fallback base=", phys_base, "size=", mem_size);
		}
	}

	uint64_t pa_of_va_base = phys_base - p->virt_base;	/* pa = va + this */
	con_hex2("PHYS", "base=", phys_base, "size=", mem_size);
	con_hex("VIRT", p->virt_base);
	con_hex("ENTRY", p->entry_va);

	/* 目标内核区域不能和 payload 自己重叠 */

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

	/* ADT 里的 dram-base/dram-size 也要跟着改（XNU 用它建 physmap）。
	 * 注意：必须字节级扫描，不能按 8 字节步进——ADT 属性值不对齐，
	 * dram-base(0x100000000) 实际落在 0x23c（%8==4），8 字节步进扫不到，
	 * 导致 ADT 里 dram-base 仍是旧值 → phys_base 错位 → tpidr_el1=0 panic。 */
	{
		volatile uint8_t *b = (volatile uint8_t *)adt_pa;
		uint64_t n = p->adt_size;
		uint64_t i = 0;
		while (i + 8 <= n) {
			int eq_base = 1, eq_size = 1;
			for (int j = 0; j < 8; j++) {
				uint8_t v = b[i + j];
				if (v != ((const uint8_t *)&p->phys_base)[j]) eq_base = 0;
				if (v != ((const uint8_t *)&p->mem_size)[j])  eq_size = 0;
			}
			if (eq_base) {
				for (int j = 0; j < 8; j++) b[i + j] = ((const uint8_t *)&phys_base)[j];
				i += 8;
			} else if (eq_size) {
				for (int j = 0; j < 8; j++) b[i + j] = ((const uint8_t *)&mem_size)[j];
				i += 8;
			} else {
				i += 1;
			}
		}
	}
	uintptr_t ba_pa = (adt_pa + p->adt_size + PAGE_16K - 1) & ~(PAGE_16K - 1);
	uintptr_t top = ba_pa + PAGE_16K;

	/* payload 必须落在内核写入区间之外（它会边拷边被读） */
	if (src_end > phys_base && src < top)
		return "payload overlaps kernel memory";

	zero64(ba_pa, PAGE_16K);
	volatile struct boot_args *ba = (volatile struct boot_args *)ba_pa;
	ba->Revision = 2;
	ba->Version = 2;
	ba->virtBase = p->virt_base;
	ba->physBase = phys_base;
	ba->memSize = mem_size;
	ba->topOfKernelData = top;
	/*
	 * XNU 的 video_console 约定：v_baseAddr 最低位为 1 表示"这是物理地址，
	 * 内核自己建映射"；为 0 且 kernel_map 已建立时会被当成虚拟地址直接用，
	 * 那样 0xB8000000 在 EL1 下访问不到 → 清屏后黑屏。
	 */
	ba->Video.v_baseAddr = FB_BASE | 1;
	ba->Video.v_display = 1;
	ba->Video.v_rowBytes = FB_STRIDE;
	ba->Video.v_width = FB_W;
	ba->Video.v_height = FB_H;
	ba->Video.v_depth = 32;
	ba->deviceTreeP = adt_pa - pa_of_va_base;
	ba->deviceTreeLength = (uint32_t)p->adt_size;
	for (int i = 0; i < BOOT_LINE_LENGTH; i++)
		ba->CommandLine[i] = p->cmdline[i];
	ba->memSizeActual = mem_size;
	con_hex2("BOOTARG", "pa=", ba_pa, "top=", top);

	uintptr_t entry_pa = p->entry_va + pa_of_va_base;
	con_hex("JUMP", entry_pa);

	/* 跳转前确认：入口处真的是代码吗？MMU 真的是关的吗？ */
	{
		volatile const uint64_t *e = (volatile const uint64_t *)entry_pa;
		uint64_t sctlr;

		con_hex("CODE@ENTRY", e[0]);
		con_hex("CODE@+8", e[1]);

		__asm__ volatile("mrs %0, sctlr_el1" : "=r"(sctlr));
		con_hex("SCTLR", sctlr);
	}
	/*
	 * XNU 冷启动时 TPIDR_EL1 应该是 0（arm_init.c:442-445 会通过
	 * machine_set_current_thread() 设置真正的 boot thread）。
	 * ABL/Gunyah 会留下脏值（真机实测 0xA76E3718），必须清成 0，
	 * 让内核走它自己的冷启动路径。不要伪造 thread 结构——
	 * 内核会读它的 machine.CpuDatap / pcpu_data_base 等字段，
	 * 假数据只会让它在异常处理里再次崩溃。
	 */
	{
		uint64_t tpidr1, tpidr0;

		__asm__ volatile("mrs %0, tpidr_el1" : "=r"(tpidr1));
		__asm__ volatile("mrs %0, tpidr_el0" : "=r"(tpidr0));
		con_hex("TPIDR_EL1-old", tpidr1);
		con_hex("TPIDR_EL0-old", tpidr0);
	}

	/*
	 * 只清 TPIDR，不伪造 thread。
	 *
	 * XNU 的 start.s:765 自己就会 msr TPIDR_EL1, xzr，随后 arm_init 通过
	 * thread_bootstrap()/machine_set_current_thread() 建立真正的 boot thread。
	 * 实测（qemu.adt 布局）TPIDR_EL1 = 0 时内核能一路跑到 idle。
	 *
	 * 之前伪造的 thread 放在 phys_base+60MB / virt_base+60MB 处，
	 * 那个地址落在内核所有段之外（kernel __LINKEDIT 到 0xfffffe000aef96b8
	 * 结束），页表里根本没有映射，内核一访问就是转换错误。
	 */
	__asm__ volatile("msr tpidr_el1, xzr" ::: "memory");
	__asm__ volatile("msr tpidr_el0, xzr" ::: "memory");
	__asm__ volatile("msr tpidrro_el0, xzr" ::: "memory");
	__asm__ volatile("isb" ::: "memory");
	{
		uint64_t now;

		__asm__ volatile("mrs %0, tpidr_el1" : "=r"(now));
		con_hex("TPIDR_EL1-new", now);
	}

	con_str("XNU", "jumping (fbcon clears screen)");

	/*
	 * 交给 XNU 之前必须回到 iBoot 那种"裸机"状态：
	 *   1) 关掉所有中断/调试异常（DAIF）
	 *   2) 把内核占用区完整刷清 D-cache（dc civac），否则关缓存后 XNU
	 *      读到的是主存里的旧数据
	 *   3) 关 SCTLR_EL1 的 M/C/I —— XNU 的 start.s 会自己建页表、开 MMU，
	 *      它假设进来时 MMU 与缓存都是关的
	 */
	__asm__ volatile("msr daifset, #15" ::: "memory");

	dc_civac_range(phys_base, top);			/* 内核 + ADT + boot_args */
	dc_civac_range(src, src + p->adt_off + p->adt_size);	/* payload 本体 */
	dc_civac_range((uintptr_t)_head, (uintptr_t)_end);	/* shim 自身（WB 映射） */

	__asm__ volatile("dsb sy; ic iallu; dsb sy; isb" ::: "memory");

	{
		uint64_t sctlr;

		__asm__ volatile("mrs %0, sctlr_el1" : "=r"(sctlr));
		con_hex("SCTLR-OLD", sctlr);
		sctlr &= ~((1ULL << 0) | (1ULL << 2) | (1ULL << 12));	/* M, C, I */
		__asm__ volatile("msr sctlr_el1, %0" :: "r"(sctlr) : "memory");
		__asm__ volatile("isb" ::: "memory");
		{
			uint64_t now;

			__asm__ volatile("mrs %0, sctlr_el1" : "=r"(now));
			con_hex("SCTLR-NEW", now);
		}
	}

	/*
	 * 关掉 MMU 后必须清 TLB —— DarwinBoot 的 DarwinEnter 就是这么做的
	 * （mrs/msr sctlr_el1 之后紧跟 tlbi vmalle1）。
	 * 否则 TLB 里残留 shim 运行时的 VA->PA 条目，内核 start.s 建好自己的
	 * 页表之后仍会命中旧映射，表现为访问看似合法的地址却触发转换错误。
	 */
	__asm__ volatile("dsb sy; isb; tlbi vmalle1; dsb sy; isb" ::: "memory");
	con_str("TLB", "invalidated (tlbi vmalle1)");

	__asm__ volatile("dsb sy; isb" ::: "memory");

	/*
	 * 跳转前的最后一步：在屏幕底部画一排可辨认的方块。
	 * XNU 的 start.s 一进去就会重设 MMU/清屏，图案消失即证明内核真的开始执行；
	 * 图案一直保留说明跳转根本没进去。
	 */
	{
		volatile uint32_t *fb = (volatile uint32_t *)FB_BASE;
		uint64_t line = (uint64_t)FB_W * 4;	/* 一行字节数 */
		uint64_t y0 = FB_H - 24;

		for (uint64_t y = y0; y < FB_H; y++) {
			for (uint64_t x = 0; x < FB_W; x++) {
				uint32_t c = ((x / 48) & 1) ? 0xffffffffu : 0xff00ffffu;

				fb[(y * line) / 4 + x] = c;
			}
		}
		con_str("XNU", "bar drawn; jumping now");
	}

	((xnu_entry_t)entry_pa)(ba_pa);
	return "xnu returned";
}
