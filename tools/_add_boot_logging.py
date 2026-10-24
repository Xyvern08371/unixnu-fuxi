"""给 XnuBootRun 加"屏幕日志"回调：每走一步就画一行，崩在哪一眼可见。"""

import io

# ---------- 1) XnuBoot.c：加日志回调 ----------
P = r"E:\ios-on-fuxi\loader\XnuBoot.c"
t = io.open(P, encoding="utf-8").read()

# 1a) 类型定义
if "XNU_LOG_FN" not in t:
    t = t.replace(
        "extern CONST UINT8  gXnuPayload[];",
        "typedef VOID (*XNU_LOG_FN)(CONST CHAR8 *Tag, UINT64 Value);\n\nextern CONST UINT8  gXnuPayload[];",
        1,
    )

# 1b) 函数签名加参数
t = t.replace(
    """  IN UINTN       FbBase,
  IN UINTN       FbPitch,
  IN UINT32      FbWidth,
  IN UINT32      FbHeight
  )""",
    """  IN UINTN       FbBase,
  IN UINTN       FbPitch,
  IN UINT32      FbWidth,
  IN UINT32      FbHeight,
  IN XNU_LOG_FN  Log
  )""",
    1,
)

# 1c) 各阶段打点
t = t.replace(
    '  if ((Payload == NULL) || (PayloadLen < PAYLOAD_SEGTAB) || !MagicOk ((CONST CHAR8 *)P)) {\n    return;\n  }',
    '  if (Log != NULL) {\n    Log ("PAYLEN", (UINT64)PayloadLen);\n  }\n\n'
    '  if ((Payload == NULL) || (PayloadLen < PAYLOAD_SEGTAB) || !MagicOk ((CONST CHAR8 *)P)) {\n'
    '    if (Log != NULL) {\n      Log ("BAD MAGIC", 0);\n    }\n    return;\n  }',
    1,
)

t = t.replace(
    '  PaOfVa    = PhysBase - VirtBase;',
    '  PaOfVa    = PhysBase - VirtBase;\n\n'
    '  if (Log != NULL) {\n'
    '    Log ("VIRTBASE", VirtBase);\n'
    '    Log ("PHYSBASE", PhysBase);\n'
    '    Log ("KEND", KernelEnd);\n'
    '    Log ("ADTSIZE", AdtSize);\n'
    '    Log ("ENTRY", EntryVa);\n'
    '    Log ("NSEGS", NSegs);\n'
    '  }',
    1,
)

t = t.replace(
    '  /* 2. ADT 放内核末尾，boot_args 放 ADT 之后（16K 对齐） */',
    '  if (Log != NULL) {\n    Log ("SEGS DONE", 0);\n  }\n\n'
    '  /* 2. ADT 放内核末尾，boot_args 放 ADT 之后（16K 对齐） */',
    1,
)

t = t.replace(
    '  /* 3. 填 boot_args */',
    '  if (Log != NULL) {\n    Log ("ADT DONE", AdtPa);\n  }\n\n'
    '  /* 3. 填 boot_args */',
    1,
)

t = t.replace(
    '  /* 4. 按范围清 D-cache，然后关 MMU/缓存并跳 __start（x0 = boot_args） */',
    '  if (Log != NULL) {\n    Log ("BOOTARGS", BaPa);\n  }\n\n'
    '  /* 4. 按范围清 D-cache，然后关 MMU/缓存并跳 __start（x0 = boot_args） */',
    1,
)

io.open(P, "w", encoding="utf-8", newline="\n").write(t)
print("XnuBoot.c 已加日志打点")

# ---------- 2) Probe.c：实现日志函数并传进去 ----------
Q = r"E:\ios-on-fuxi\loader\Probe.c"
c = io.open(Q, encoding="utf-8").read()

# 2a) 声明
c = c.replace(
    "extern VOID         XnuBootRun (CONST VOID *, UINTN, UINTN, UINTN, UINT32, UINT32);",
    "extern VOID         XnuBootRun (CONST VOID *, UINTN, UINTN, UINTN, UINT32, UINT32,\n"
    "                                VOID (*)(CONST CHAR8 *, UINT64));",
    1,
)

# 2b) 日志函数（用自绘字体，EBS 之后也能画）
if "XnuScreenLog" not in c:
    logfn = '''
/* EBS 之后 ConOut 已经没了，日志用自己的点阵字体画到屏幕 */
STATIC UINT32  mLogY;

STATIC VOID
XnuScreenLog (
  IN CONST CHAR8  *Tag,
  IN UINT64        Value
  )
{
  CHAR8  Line[40];
  UINTN  I;
  UINTN  N;

  for (N = 0; Tag[N] != 0 && N < 20; N++) {
    Line[N] = Tag[N];
  }
  Line[N++] = '=';
  for (I = 0; I < 16; I++) {
    UINTN  Shift = (15 - I) * 4;
    UINTN  D     = (UINTN)((Value >> Shift) & 0xF);

    Line[N++] = (CHAR8)((D < 10) ? ('0' + D) : ('A' + D - 10));
  }
  Line[N] = 0;

  DrawString (20, mLogY, Line, 0xFFFFFFFF);
  mLogY += 24;
}

'''
    c = c.replace("STATIC EFI_GUID  mFdtTableGuid = {", logfn + "STATIC EFI_GUID  mFdtTableGuid = {", 1)

# 2c) 调用处传日志函数 + 初始化行高
c = c.replace(
    """      if (XnuPayloadSize () > 0) {
        XnuBootRun (XnuPayloadAddr (), XnuPayloadSize (),
                    (UINTN) mFb, (UINTN) mFbPitch, mFbW, mFbH);
      }""",
    """      if (XnuPayloadSize () > 0) {
        Fill (0xFF000000);
        mLogY = 40;
        XnuScreenLog ("EBS OK", XnuPayloadSize ());
        XnuBootRun (XnuPayloadAddr (), XnuPayloadSize (),
                    (UINTN) mFb, (UINTN) mFbPitch, mFbW, mFbH, XnuScreenLog);
        XnuScreenLog ("RETURNED", 0);
      }""",
    1,
)

io.open(Q, "w", encoding="utf-8", newline="\n").write(c)
print("Probe.c 已接上屏幕日志")

# 自检
for f in (P, Q):
    s = io.open(f, encoding="utf-8").read()
    print(f, "大括号:", s.count("{"), "vs", s.count("}"), "| 日志点数:", s.count("XnuScreenLog"))
