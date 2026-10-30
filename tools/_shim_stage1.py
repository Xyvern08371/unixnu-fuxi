"""shim 的第一版适配：
1) 控制台改到 fuxi 真正的 splash 帧缓冲 0xB8000000
2) 拿不到 payload 时不要探测 UFS（未映射，会崩），直接停在屏幕上
3) 屏幕标题改成 fuxi
"""

import io

# 1) console.h: FB_BASE
P = r"E:\ios-on-fuxi\loader-shim-fuxi\console.h"
t = io.open(P, encoding="utf-8").read()
t = t.replace("#define FB_BASE\t\t0xB0000000UL", "#define FB_BASE\t\t0xB8000000UL")
io.open(P, "w", encoding="utf-8", newline="\n").write(t)

for line in io.open(P, encoding="utf-8").read().split("\n"):
    if "FB_BASE" in line or "FB_W" in line or "FB_H" in line or "FB_STRIDE" in line:
        print("console.h:", line.strip())

# 2) shim.c: 标题 + 不探测 UFS
Q = r"E:\ios-on-fuxi\loader-shim-fuxi\shim.c"
c = io.open(Q, encoding="utf-8").read()

c = c.replace('con_str("SHIM", "sweet milestone 4: xnu loader");',
              'con_str("SHIM", "fuxi bare-metal xnu loader");')

old = """	/* No payload: probe the internal UFS while the MMU is still off. */
	stage = "ufs";
	test_ufs();"""
new = """	/*
	 * fuxi: 拿不到 payload 时不要探测 UFS——UFS 寄存器此刻多半未映射，
	 * 访问会同步异常，设备直接重启回 fastboot，什么都看不到。
	 * 停在屏幕上，让上面打印的错误信息留着。
	 */
	if (why != 0) {
		con_str("HALT", "no payload, staying here");
		for (;;) {
			__asm__ volatile("wfi");
		}
	}

	stage = "ufs";
	test_ufs();"""
assert old in c, "ufs block not found"
c = c.replace(old, new, 1)
io.open(Q, "w", encoding="utf-8", newline="\n").write(c)
print("\nshim.c: 已加「无 payload 就停机」")

for i, line in enumerate(io.open(Q, encoding="utf-8").read().split("\n"), 1):
    if "fuxi bare-metal" in line or "no payload, staying here" in line:
        print("  L%d: %s" % (i, line.strip()))
