"""把 AsmXnuJump 的 br 换成原地死循环，单独验证「关 MMU 后写显存」是否可行。"""

import io

P = r"E:\ios-on-fuxi\loader\xnu_jump.S"
t = io.open(P, encoding="utf-8").read()

if "5:" in t and "b       5b" in t:
    print("已经改过了")
else:
    old = """    mov     x0, x4
    br      x3"""
    assert old in t, "br anchor not found"
    new = """    // fuxi probe: do not jump yet, spin here to isolate the MMU-off write test
5:
    wfi
    b       5b

    mov     x0, x4
    br      x3"""
    t = t.replace(old, new, 1)
    io.open(P, "w", encoding="utf-8", newline="\n").write(t)
    print("AsmXnuJump: br replaced with spin loop")

lines = io.open(P, encoding="utf-8").read().split("\n")
for i, l in enumerate(lines, 1):
    if "5:" in l or "b       5b" in l or "br      x3" in l:
        print("  L%d: %r" % (i, l))
