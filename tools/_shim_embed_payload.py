"""把 payload 内嵌进 shim Image：不依赖 ABL 的 ramdisk（fuxi 上 boot 分区基本不放 ramdisk）。

改动：
1) shim.ld        加 _payload_start（Image 末尾 4K 对齐处）
2) start.S        记录运行时镜像基址到 g_image_base
3) shim.c         用 g_image_base + _payload_start 得到 payload 地址，传给 loader
4) loader.c       loader_boot 优先用内嵌 payload
5) build-shim.sh  把 payload 追加到 Image 末尾
6) boot.img 打包  ramdisk 用 1 字节（和能启动的 UEFI 镜像一致）
"""

import io

# ---------- 1) shim.ld ----------
P = r"E:\ios-on-fuxi\loader-shim-fuxi\shim.ld"
t = io.open(P, encoding="utf-8").read()
if "_payload_start" not in t:
    t = t.replace("\t_end = .;", "\t_end = .;\n\t. = ALIGN(4096);\n\t_payload_start = .;", 1)
    io.open(P, "w", encoding="utf-8", newline="\n").write(t)
    print("shim.ld: +_payload_start")

# ---------- 2) start.S ----------
S = r"E:\ios-on-fuxi\loader-shim-fuxi\start.S"
s = io.open(S, encoding="utf-8").read()
if "g_image_base" not in s:
    old = """_start:
	msr	daifset, #0xf
	mov	x19, x0			/* DTB pointer from ABL */"""
    new = """_start:
	msr	daifset, #0xf
	mov	x19, x0			/* DTB pointer from ABL */

	/* 记录运行时镜像基址（我们可能被加载到任意地址） */
	adr	x1, _head
	adrp	x2, g_image_base
	add	x2, x2, :lo12:g_image_base
	str	x1, [x2]"""
    assert old in s, "start.S anchor not found"
    s = s.replace(old, new, 1)
    io.open(S, "w", encoding="utf-8", newline="\n").write(s)
    print("start.S: +g_image_base 记录")

# ---------- 3) shim.c ----------
C = r"E:\ios-on-fuxi\loader-shim-fuxi\shim.c"
c = io.open(C, encoding="utf-8").read()
if "g_payload_ptr" not in c:
    c = c.replace("void shim_main(uint64_t dtb)",
                  """uint64_t g_image_base;
const void *g_payload_ptr;
extern char _payload_start[];

void shim_main(uint64_t dtb)""", 1)
    old_call = "\tconst char *why = loader_boot(dtb);"
    new_call = """	/* payload 内嵌在镜像末尾：基址 + 链接期偏移 */
	g_payload_ptr = (const void *)(g_image_base + (uintptr_t)_payload_start);
	con_hex("SELF", g_image_base);
	con_hex("PAYLOAD", (uint64_t)g_payload_ptr);
	const char *why = loader_boot(dtb);"""
    assert old_call in c, "loader_boot call not found"
    c = c.replace(old_call, new_call, 1)
    io.open(C, "w", encoding="utf-8", newline="\n").write(c)
    print("shim.c: 已用内嵌 payload")

# ---------- 4) loader.c ----------
L = r"E:\ios-on-fuxi\loader-shim-fuxi\loader.c"
l = io.open(L, encoding="utf-8").read()
if "g_payload_ptr" not in l:
    l = l.replace("const char *loader_boot(uintptr_t dtb)\n{",
                  """extern const void *g_payload_ptr;

const char *loader_boot(uintptr_t dtb)
{
	if (g_payload_ptr != 0) {
		const struct payload *p = (const struct payload *)g_payload_ptr;
		if (!magic_ok(p->magic))
			return "embedded payload: bad magic";
		return loader_copy(p);
	}
""", 1)
    io.open(L, "w", encoding="utf-8", newline="\n").write(l)
    print("loader.c: loader_boot 优先用内嵌 payload（需要 loader_copy 拆分）")

# ---------- 5) build-shim.sh ----------
B = r"E:\ios-on-fuxi\loader-shim-fuxi\build-shim.sh"
b = io.open(B, encoding="utf-8").read()
if "PAYLOAD_FILE" not in b:
    b = b.replace('echo "=== shim 编译完成 ==="',
                  '''if [ -n "${PAYLOAD_FILE:-}" ]; then
  echo "=== 内嵌 payload ==="
  cat "$PAYLOAD_FILE" >> "$OUT/Image"
fi

echo "=== shim 编译完成 ==="''')
    io.open(B, "w", encoding="utf-8", newline="\n").write(b)
    print("build-shim.sh: +payload 内嵌")

# ---------- 6) packer ----------
M = r"E:\ios-on-fuxi\tools\mkshim_bootimg.py"
m = io.open(M, encoding="utf-8").read()
m = m.replace('ap.add_argument("--ramdisk", required=True)',
              'ap.add_argument("--ramdisk", default="")')
m = m.replace('    ramdisk = open(a.ramdisk, "rb").read()',
              '    ramdisk = open(a.ramdisk, "rb").read() if a.ramdisk else b"\\0"')
io.open(M, "w", encoding="utf-8", newline="\n").write(m)
print("mkshim_bootimg.py: ramdisk 可选（默认 1 字节）")
