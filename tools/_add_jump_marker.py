"""在 AsmXnuJump 内部加探针：关完 MMU 后先往显存画一块绿色，再 br 到内核。

绿色出现 = 关 MMU 之后的写显存正常，问题只剩 br 那一条指令。
"""

import io

P = r"E:\ios-on-fuxi\loader\xnu_jump.S"
t = io.open(P, encoding="utf-8").read()

if "MARKER_AFTER_MMU_OFF" in t:
    print("已经加过了")
else:
    anchor = """    mov     x0, x4
    br      x3"""
    assert anchor in t, "br 锚点没找到"

    probe = """    // ---------------- MARKER_AFTER_MMU_OFF ----------------
    // MMU 已关，先往帧缓冲左上角画一块 64x64 的绿色方块。
    // 看到绿色 = 关 MMU 之后的写显存正常 -> 问题只剩 br 指令。
    mov     x5, #0xB0000000
    mov     x6, #4096
    mov     w7, #0x0000FF00
3:
    str     w7, [x5], #4
    subs    x6, x6, #1
    b.ne    3b
    dsb     sy

    mov     x0, x4
    br      x3"""

    t = t.replace(anchor, probe, 1)
    io.open(P, "w", encoding="utf-8", newline="\n").write(t)
    print("xnu_jump.S: 已加关 MMU 后的绿色探针")

s = io.open(P, encoding="utf-8").read()
print("MARKER_AFTER_MMU_OFF 存在:", "MARKER_AFTER_MMU_OFF" in s)
