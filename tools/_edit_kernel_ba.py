import io
import sys

P = r"E:\ios-on-fuxi\payload\kernel.c"
s = io.open(P, encoding="utf-8").read()

idx = s.find("void kernel_main(")
if idx < 0:
    print("找不到 kernel_main")
    sys.exit(1)

tail = r'''/* ---- 与目标 XNU 的 pexpert/arm64/boot.h 一致的 boot_args ---- */

typedef struct {
    u64 v_baseAddr;
    u64 v_display;
    u64 v_rowBytes;
    u64 v_width;
    u64 v_height;
    u64 v_depth;
} boot_video;

typedef struct {
    u16     revision;
    u16     version;
    u64     virt_base;
    u64     phys_base;
    u64     mem_size;
    u64     top_of_kernel_data;
    boot_video video;
    u32     machine_type;
    void   *device_tree_p;
    u32     device_tree_length;
    char    command_line[608];
    u64     boot_flags;
    u64     mem_size_actual;
} boot_args;

void kernel_main(u64 ba_ptr)
{
    const boot_args *ba = (const boot_args *)ba_ptr;
    char num[20];
    u32 y;
    u32 magic = 0;

    if (ba == 0) {
        return;
    }

    /* 用 boot_args 里的 Video 字段配置输出 */
    g_fb     = ba->video.v_baseAddr;
    g_pitch  = ba->video.v_rowBytes / 4;
    g_height = ba->video.v_height;

    if (g_fb == 0 || g_pitch == 0) {
        for (;;) {
            __asm__ __volatile__("wfi");
        }
    }

    if (ba->device_tree_p) {
        const u8 *p = (const u8 *)ba->device_tree_p;
        magic = ((u32)p[0] << 24) | ((u32)p[1] << 16) |
                ((u32)p[2] << 8)  | (u32)p[3];
    }

    fill(0xFF000000);

    y = 100;
    draw_string(40, y, "XNU HANDOFF", 0xFFFFFFFF);      y += LINE_H;
    draw_string(40, y, "KERNEL RUNNING", 0xFFFFFFFF);   y += LINE_H;

    draw_string(40, y, "REV", 0xFFFFFFFF);              y += LINE_H;
    hex((u64)ba->revision, num);
    draw_string(40, y, num, 0xFFFFFFFF);                y += LINE_H;

    draw_string(40, y, "PHYSBASE", 0xFFFFFFFF);         y += LINE_H;
    hex(ba->phys_base, num);
    draw_string(40, y, num, 0xFFFFFFFF);                y += LINE_H;

    draw_string(40, y, "MEMSIZE", 0xFFFFFFFF);          y += LINE_H;
    hex(ba->mem_size, num);
    draw_string(40, y, num, 0xFFFFFFFF);                y += LINE_H;

    draw_string(40, y, "DTB", 0xFFFFFFFF);              y += LINE_H;
    hex((u64)ba->device_tree_p, num);
    draw_string(40, y, num, 0xFFFFFFFF);                y += LINE_H;

    draw_string(40, y, "DTLEN", 0xFFFFFFFF);            y += LINE_H;
    hex((u64)ba->device_tree_length, num);
    draw_string(40, y, num, 0xFFFFFFFF);                y += LINE_H;

    draw_string(40, y, magic == 0xD00DFEEDUL ? "DT OK" : "DT BAD", 0xFFFFFFFF);
    y += LINE_H;

    draw_string(40, y, "CMDLINE", 0xFFFFFFFF);          y += LINE_H;
    draw_string(40, y, ba->command_line, 0xFFFFFFFF);

    flush_fb();

    for (;;) {
        __asm__ __volatile__("wfi");
    }
}

/* 编译器可能生成对 memcpy/memset 的调用（即使 -ffreestanding），这里自己提供 */
void *memcpy(void *dst, const void *src, unsigned long n)
{
    unsigned char       *d = (unsigned char *)dst;
    const unsigned char *s = (const unsigned char *)src;
    unsigned long        i;

    for (i = 0; i < n; i++) {
        d[i] = s[i];
    }
    return dst;
}

void *memset(void *dst, int c, unsigned long n)
{
    unsigned char *d = (unsigned char *)dst;
    unsigned long  i;

    for (i = 0; i < n; i++) {
        d[i] = (unsigned char)c;
    }
    return dst;
}
'''

s = s[:idx] + tail
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("kernel.c 已改为读取 boot_args")
for ln, line in enumerate(s.split("\n"), 1):
    if any(k in line for k in ("void kernel_main", "ba->video", "XNU HANDOFF")):
        print("  L%d: %s" % (ln, line.strip()[:80]))
