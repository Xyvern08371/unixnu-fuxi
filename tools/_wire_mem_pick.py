"""把 XnuMem 接进去：选内存 + 改 ADT + 用选中的 phys_base 拷贝。"""

import io

# ---------- 1) XnuBoot.c：用选中的内存 ----------
P = r"E:\ios-on-fuxi\loader\XnuBoot.c"
t = io.open(P, encoding="utf-8").read()

# 1a) 外部符号
if "XnuPickPhysRegion" not in t:
    t = t.replace(
        "extern CONST UINT8  gXnuPayload[];",
        "extern UINT64      mXnuPhysBase;\nextern UINT64      mXnuPhysSize;\n"
        "extern UINT32      XnuPatchAdt (UINT8 *Adt, UINTN Len, UINT64 Base, UINT64 Size);\n\n"
        "extern CONST UINT8  gXnuPayload[];",
        1,
    )

# 1b) 用选中值覆盖 payload 里的 phys_base / mem_size，并改 ADT
old = """  PaOfVa    = PhysBase - VirtBase;"""
new = """  /* 用 EFI 内存图挑出来的真实可用内存覆盖 ADT 里的硬编码值 */
  if (mXnuPhysBase != 0) {
    PhysBase = mXnuPhysBase;
    MemSize  = mXnuPhysSize;
    if (Log != NULL) {
      Log ("USE PICKED", PhysBase);
    }
  }

  PaOfVa    = PhysBase - VirtBase;"""
assert old in t
t = t.replace(old, new, 1)

# 1c) 写 ADT 之后立即改属性
old2 = """  AdtPa = KernelEnd + PaOfVa;
  Copy64 ((UINTN)AdtPa, (UINTN)(P + AdtOff), (UINTN)AdtSize);"""
new2 = """  AdtPa = KernelEnd + PaOfVa;
  Copy64 ((UINTN)AdtPa, (UINTN)(P + AdtOff), (UINTN)AdtSize);

  /* 把 ADT 里的 dram-base/dram-size 改成实际使用的那块内存 */
  {
    UINT32  Patched;

    Patched = XnuPatchAdt ((UINT8 *)(UINTN)AdtPa, (UINTN)AdtSize, PhysBase, MemSize);
    if (Log != NULL) {
      Log ("ADT PATCHED", (UINT64)Patched);
    }
  }"""
assert old2 in t
t = t.replace(old2, new2, 1)

io.open(P, "w", encoding="utf-8", newline="\n").write(t)
print("XnuBoot.c 已接入内存选择")

# ---------- 2) Probe.c：EBS 前先挑内存 ----------
Q = r"E:\ios-on-fuxi\loader\Probe.c"
c = io.open(Q, encoding="utf-8").read()

if "XnuPickPhysRegion" not in c:
    c = c.replace(
        "extern EFI_STATUS   XnuLoadFromFv (VOID **Buf, UINTN *Size,",
        "extern UINT32       XnuPickPhysRegion (VOID (*Log)(CONST CHAR8 *, UINT64));\n"
        "extern EFI_STATUS   XnuLoadFromFv (VOID **Buf, UINTN *Size,",
        1,
    )
    c = c.replace(
        """      XnuLoadFromFv (&mXnuBuf, &mXnuBufSize, XnuScreenLog);""",
        """      XnuPickPhysRegion (XnuScreenLog);
      XnuLoadFromFv (&mXnuBuf, &mXnuBufSize, XnuScreenLog);""",
        1,
    )
io.open(Q, "w", encoding="utf-8", newline="\n").write(c)
print("Probe.c 已调用 XnuPickPhysRegion")

# ---------- 3) INF ----------
inf = r"E:\ios-on-fuxi\loader\Probe.inf"
s = io.open(inf, encoding="utf-8").read()
if "XnuMem.c" not in s:
    s = s.replace("  XnuLoad.c\n", "  XnuLoad.c\n  XnuMem.c\n")
    io.open(inf, "w", encoding="utf-8", newline="\n").write(s)
    print("INF 已加 XnuMem.c")

# ---------- 4) CI 复制 ----------
W = r"E:\ios-on-fuxi\.github\workflows\build-fuxi-uefi.yml"
w = io.open(W, encoding="utf-8").read()
w = w.replace(
    "loader/XnuLoad.c loader/XnuFv.c loader/XnuUfs.c",
    "loader/XnuLoad.c loader/XnuMem.c loader/XnuFv.c loader/XnuUfs.c",
)
io.open(W, "w", encoding="utf-8", newline="\n").write(w)
print("CI 复制列表已更新")
