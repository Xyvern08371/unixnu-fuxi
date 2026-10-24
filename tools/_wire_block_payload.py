import io

# ---------- 1) Probe.inf：加 XnuLoad.c + BlockIo 协议 ----------
inf = r"E:\ios-on-fuxi\loader\Probe.inf"
s = io.open(inf, encoding="utf-8").read()
if "XnuLoad.c" not in s:
    s = s.replace("  XnuBoot.c\n", "  XnuBoot.c\n  XnuLoad.c\n")
if "gEfiBlockIoProtocolGuid" not in s:
    s = s.replace("[Protocols]\n", "[Protocols]\n  gEfiBlockIoProtocolGuid\n")
io.open(inf, "w", encoding="utf-8", newline="\n").write(s)
print(s[s.index("[Sources]"):s.index("[Packages]")])
print(s[s.index("[Protocols]"):s.index("[LibraryClasses]")])

# ---------- 2) Probe.c：EBS 之前加载 payload，退出后用它 ----------
pc = r"E:\ios-on-fuxi\loader\Probe.c"
c = io.open(pc, encoding="utf-8").read()

# 2a) 声明
c = c.replace(
    "extern VOID         XnuBootRun (CONST VOID *, UINTN, UINTN, UINTN, UINT32, UINT32,",
    "extern EFI_STATUS   XnuLoadFromBlock (VOID **Buf, UINTN *Size);\n"
    "extern VOID         XnuBootRun (CONST VOID *, UINTN, UINTN, UINTN, UINT32, UINT32,",
    1,
)

# 2b) 全局缓冲
if "mXnuBuf" not in c:
    c = c.replace(
        "STATIC UINTN       mMapBufSize;",
        "STATIC UINTN       mMapBufSize;\nSTATIC VOID       *mXnuBuf;\nSTATIC UINTN       mXnuBufSize;",
        1,
    )

# 2c) EBS 之前加载
c = c.replace(
    "    /* 标记: 已经准备调用 ExitBootServices（画在屏幕上，和 EBS 之后的日志区分开） */",
    """    /* 先试着从块设备（dtbo 分区）把 XNU payload 读进内存：EBS 之后协议就没了 */
    if (XnuPayloadSize () == 0) {
      if (!EFI_ERROR (XnuLoadFromBlock (&mXnuBuf, &mXnuBufSize))) {
        if (mXnuBufSize > 0) {
          Fill (0xFF001800);
          mLogY = 40;
          XnuScreenLog ("BLOCK PAYLOAD", mXnuBufSize);
          XnuScreenLog ("EMBEDDED", XnuPayloadSize ());
        }
      }
    }

    /* 标记: 已经准备调用 ExitBootServices（画在屏幕上，和 EBS 之后的日志区分开） */""",
    1,
)

# 2d) 退出后：优先用块设备读到的缓冲
c = c.replace(
    """      if (XnuPayloadSize () > 0) {
        Fill (0xFF000000);
        mLogY = 40;
        XnuScreenLog ("EBS OK", XnuPayloadSize ());
        XnuBootRun (XnuPayloadAddr (), XnuPayloadSize (),
                    (UINTN) mFb, (UINTN) mFbPitch, mFbW, mFbH, XnuScreenLog);
        XnuScreenLog ("RETURNED", 0);
      }""",
    """      if (mXnuBufSize > 0 || XnuPayloadSize () > 0) {
        Fill (0xFF000000);
        mLogY = 40;
        XnuScreenLog ("EBS OK", (mXnuBufSize > 0) ? mXnuBufSize : XnuPayloadSize ());
        XnuBootRun ((mXnuBufSize > 0) ? mXnuBuf : XnuPayloadAddr (),
                    (mXnuBufSize > 0) ? mXnuBufSize : XnuPayloadSize (),
                    (UINTN) mFb, (UINTN) mFbPitch, mFbW, mFbH, XnuScreenLog);
        XnuScreenLog ("RETURNED", 0);
      }""",
    1,
)

io.open(pc, "w", encoding="utf-8", newline="\n").write(c)
print("Probe.c 已接上块设备加载")
print("大括号:", c.count("{"), "vs", c.count("}"))
print("mXnuBuf 出现:", c.count("mXnuBuf"))
