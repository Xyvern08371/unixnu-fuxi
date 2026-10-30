"""接上自己的 MMU（接管 TTBR0）。"""

import io

# ---------- 1) Probe.c：EBS 成功后先装页表 ----------
Q = r"E:\ios-on-fuxi\loader\Probe.c"
c = io.open(Q, encoding="utf-8").read()

if "XnuMmuInstall" not in c:
    c = c.replace(
        "extern UINT32       XnuPickPhysRegion (VOID (*Log)(CONST CHAR8 *, UINT64));",
        "extern UINT32       XnuMmuInstall (UINTN WbLo, UINTN WbHi);\n"
        "extern UINT32       XnuPickPhysRegion (VOID (*Log)(CONST CHAR8 *, UINT64));",
        1,
    )
    c = c.replace(
        """      if (mXnuBufSize > 0 || XnuPayloadSize () > 0) {
        Fill (0xFF000000);""",
        """      if (mXnuBufSize > 0 || XnuPayloadSize () > 0) {
        /* 接管 MMU：自己建恒等映射，之后 4GB 以上也能访问 */
        XnuMmuInstall (0, 0);
        Fill (0xFF000000);""",
        1,
    )
    c = c.replace(
        """        XnuScreenLog ("EBS OK", (mXnuBufSize > 0) ? mXnuBufSize : XnuPayloadSize ());""",
        """        XnuScreenLog ("EBS OK", (mXnuBufSize > 0) ? mXnuBufSize : XnuPayloadSize ());
        XnuScreenLog ("MMU OWN", 1);""",
        1,
    )
    io.open(Q, "w", encoding="utf-8", newline="\n").write(c)
    print("Probe.c 已接 XnuMmuInstall")

# ---------- 2) INF ----------
inf = r"E:\ios-on-fuxi\loader\Probe.inf"
s = io.open(inf, encoding="utf-8").read()
if "XnuMmu.c" not in s:
    s = s.replace("  XnuMem.c\n", "  XnuMem.c\n  XnuMmu.c\n")
    io.open(inf, "w", encoding="utf-8", newline="\n").write(s)
    print("INF 已加 XnuMmu.c")

# ---------- 3) CI 复制 ----------
W = r"E:\ios-on-fuxi\.github\workflows\build-fuxi-uefi.yml"
w = io.open(W, encoding="utf-8").read()
w = w.replace("loader/XnuMem.c loader/XnuFv.c", "loader/XnuMem.c loader/XnuMmu.c loader/XnuFv.c")
io.open(W, "w", encoding="utf-8", newline="\n").write(w)
print("CI 复制列表已更新")

# 校验
for f in (Q, r"E:\ios-on-fuxi\loader\XnuMmu.c"):
    t = io.open(f, encoding="utf-8").read()
    print(f.split("\\")[-1], "大括号:", t.count("{"), "vs", t.count("}"))
