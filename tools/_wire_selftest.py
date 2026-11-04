"""接入跳转自测：这轮不跳 XNU，跳自测桩刷整屏颜色。"""

import io

Q = r"E:\ios-on-fuxi\loader\Probe.c"
c = io.open(Q, encoding="utf-8").read()

# 声明
if "AsmXnuSelfTest" not in c:
    c = c.replace(
        "extern UINT32       XnuMmuInstall (UINTN WbLo, UINTN WbHi);",
        "extern UINT32       XnuMmuInstall (UINTN WbLo, UINTN WbHi);\n"
        "extern VOID         AsmXnuSelfTest (UINTN Fb, UINTN Bytes, UINT32 Color);",
        1,
    )

# 在调用 XnuBootRun 之前插入自测（本轮直接停在那里）
old = """        XnuScreenLog ("EBS OK", (mXnuBufSize > 0) ? mXnuBufSize : XnuPayloadSize ());
        XnuScreenLog ("MMU OWN", 1);
        XnuBootRun ((mXnuBufSize > 0) ? mXnuBuf : XnuPayloadAddr (),"""
new = """        XnuScreenLog ("EBS OK", (mXnuBufSize > 0) ? mXnuBufSize : XnuPayloadSize ());

        /* 跳转自测：不跳 XNU，改成关 MMU/缓存后把整屏刷成红色并停住。
           能看到红色 = 关 MMU 这套动作本身是好的。 */
        XnuScreenLog ("SELFTEST", (UINT64) mFbSize);
        AsmXnuSelfTest ((UINTN) mFb, (UINTN) mFbSize, 0xFFFF0000U);

        XnuBootRun ((mXnuBufSize > 0) ? mXnuBuf : XnuPayloadAddr (),"""
assert old in c, "调用点没找到"
c = c.replace(old, new, 1)
io.open(Q, "w", encoding="utf-8", newline="\n").write(c)
print("已接入自测桩")
print("大括号:", c.count("{"), "vs", c.count("}"))
