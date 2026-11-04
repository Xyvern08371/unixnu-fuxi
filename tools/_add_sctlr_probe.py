"""验证 SCTLR_EL1.M 到底能不能被清掉（在 EL2 hypervisor 干预下可能被忽略）。

做法：读 SCTLR → 清 M → 立刻读回 → 恢复原值 返回。全程在汇编里完成，
最后恢复 MMU 再 ret，所以 C 代码和栈都安全。
"""

import io

P = r"E:\ios-on-fuxi\loader\xnu_jump.S"
t = io.open(P, encoding="utf-8").read()

if "AsmXnuTryMmuOff" not in t:
    fn = """// ---------------------------------------------------------------------------
// void AsmXnuTryMmuOff(UINT64 out[2])
//   out[0] = 清 M 之前的 SCTLR_EL1
//   out[1] = 清 M 之后立刻读回的 SCTLR_EL1
// 结束时恢复原值（MMU 保持开启），所以对调用者安全。
// ---------------------------------------------------------------------------
.global AsmXnuTryMmuOff
.type   AsmXnuTryMmuOff, %function
AsmXnuTryMmuOff:
    mrs     x2, sctlr_el1
    str     x2, [x0]
    bic     x3, x2, #0x1
    msr     sctlr_el1, x3
    isb
    mrs     x4, sctlr_el1
    str     x4, [x0, #8]
    msr     sctlr_el1, x2
    isb
    ret
.size   AsmXnuTryMmuOff, . - AsmXnuTryMmuOff

"""
    anchor = "// ---------------------------------------------------------------------------\n// void AsmXnuJump(UINTN entry_pa, UINTN boot_args_pa)"
    assert anchor in t
    t = t.replace(anchor, fn + anchor, 1)
    io.open(P, "w", encoding="utf-8", newline="\n").write(t)
    print("xnu_jump.S: 已加 AsmXnuTryMmuOff")

# XnuBoot.c 调用并打印
Q = r"E:\ios-on-fuxi\loader\XnuBoot.c"
c = io.open(Q, encoding="utf-8").read()

if "SCTLR OFF" not in c:
    d = """VOID
AsmXnuDcacheInvalidateRange (
  IN UINTN  Start,
  IN UINTN  End
  );"""
    assert d in c
    c = c.replace(d, d + """

VOID
AsmXnuTryMmuOff (
  OUT UINT64  Out[2]
  );""", 1)

    anchor2 = '    CopyMem (&Head, (VOID *)(UINTN)EntryPa, 8);'
    assert anchor2 in c
    probe = """    /*
     * 验证 MMU 到底能不能关：如果 EL2 上有 hypervisor 设了 HCR_EL2.TVM，
     * EL1 写 SCTLR_EL1 会被静默忽略，那么后面 br 到物理地址就会失败。
     */
    {
      UINT64  Mm[2];

      AsmXnuTryMmuOff (Mm);
      if (Log != NULL) {
        Log ("SCTLR BEFORE", Mm[0]);
        Log ("SCTLR AFTER", Mm[1]);
        Log ("MMU CAN OFF", (Mm[1] & 1ULL) == 0 ? 1 : 0);
      }
    }

""" + anchor2
    c = c.replace(anchor2, probe, 1)
    io.open(Q, "w", encoding="utf-8", newline="\n").write(c)
    print("XnuBoot.c: 已加 SCTLR 验证探针")

for f in (P, Q):
    s = io.open(f, encoding="utf-8").read()
    print(f.split("\\")[-1], "大括号:", s.count("{"), "vs", s.count("}"))
