"""加缓存自校验：作废内核区域的 D-cache 行，再从内存重读入口字节。

目的：如果"清缓存前读到的"和"作废缓存后从内存读到的"不一致，
说明 dc cvac 没把数据真正写回内存 —— 真机上内核就执行不到正确代码。
"""

import io

# 1) 在 xnu_jump.S 里加 AsmXnuDcacheInvalidateRange
P = r"E:\ios-on-fuxi\loader\xnu_jump.S"
t = io.open(P, encoding="utf-8").read()

if "AsmXnuDcacheInvalidateRange" not in t:
    anchor = """// ---------------------------------------------------------------------------
// void AsmXnuJump(UINTN entry_pa, UINTN boot_args_pa)"""
    assert anchor in t, "锚点没找到"

    fn = """// ---------------------------------------------------------------------------
// void AsmXnuDcacheInvalidateRange(UINTN start, UINTN end)
// 作废 D-cache 行（不写回）：用来强制后续读取走内存，验证清缓存是否有效
// ---------------------------------------------------------------------------
.global AsmXnuDcacheInvalidateRange
.type   AsmXnuDcacheInvalidateRange, %function
AsmXnuDcacheInvalidateRange:
    mrs     x2, ctr_el0
    ubfx    x3, x2, #16, #4
    mov     x4, #4
    lsl     x4, x4, x3
    sub     x5, x4, #1
    bic     x0, x0, x5
4:
    dc      ivac, x0
    add     x0, x0, x4
    cmp     x0, x1
    b.lo    4b
    dsb     sy
    ret
.size   AsmXnuDcacheInvalidateRange, . - AsmXnuDcacheInvalidateRange

""" + anchor
    t = t.replace(anchor, fn, 1)
    io.open(P, "w", encoding="utf-8", newline="\n").write(t)
    print("xnu_jump.S: 已加 AsmXnuDcacheInvalidateRange")

# 2) XnuBoot.c：清缓存后作废 + 重读校验
Q = r"E:\ios-on-fuxi\loader\XnuBoot.c"
c = io.open(Q, encoding="utf-8").read()

if "CODE@MEM" not in c:
    # 声明
    c = c.replace(
        """VOID
AsmXnuDcacheCleanRange (
  IN UINTN  Start,
  IN UINTN  End
  );""",
        """VOID
AsmXnuDcacheCleanRange (
  IN UINTN  Start,
  IN UINTN  End
  );

VOID
AsmXnuDcacheInvalidateRange (
  IN UINTN  Start,
  IN UINTN  End
  );""",
        1,
    )

    # 在 CODE@ENTRY 读取之后、刷屏之前插入校验
    old = """      CopyMem (&Head, (VOID *)(UINTN)EntryPa, 8);
      if (Log != NULL) {
        Log ("ENTRY PA", EntryPa);
        Log ("CODE@ENTRY", Head);
      }"""
    new = """      CopyMem (&Head, (VOID *)(UINTN)EntryPa, 8);

      /*
       * 自校验：把内核区域的 D-cache 行作废，再从内存重读同样的 8 字节。
       * 两个值不一致 = dc cvac 没真正写回内存，真机上内核会执行到垃圾。
       */
      AsmXnuDcacheInvalidateRange ((UINTN)PhysBase, (UINTN)(KernelEnd + PaOfVa));
      {
        UINT64  Head2;

        CopyMem (&Head2, (VOID *)(UINTN)EntryPa, 8);
        if (Log != NULL) {
          Log ("ENTRY PA", EntryPa);
          Log ("CODE@ENTRY", Head);
          Log ("CODE@MEM", Head2);
        }
      }"""
    assert old in c, "CODE@ENTRY 块没找到"
    c = c.replace(old, new, 1)
    io.open(Q, "w", encoding="utf-8", newline="\n").write(c)
    print("XnuBoot.c: 已加缓存自校验（CODE@MEM）")

for f in (P, Q):
    s = io.open(f, encoding="utf-8").read()
    print(f.split("\\")[-1], "大括号:", s.count("{"), "vs", s.count("}"))
