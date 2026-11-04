import io
import sys

P = r"E:\ios-on-fuxi\loader\Probe.c"
s = io.open(P, encoding="utf-8").read()

# 1) 把扫描逻辑抽成函数，插在 PayloadEntry 之前
anchor = 'STATIC __attribute__((unused)) VOID\nPayloadEntry ('
idx = s.find(anchor)
if idx < 0:
    print("找不到 PayloadEntry")
    sys.exit(1)

func = r'''/** 在 EFI 配置表里找设备树: 先按 GUID, 再按魔数兜底。
    注意: 驱动入口时配置表还没齐, 必须在退出前再调一次。 */
STATIC __attribute__((unused)) VOID
FindFdt (
  VOID
  )
{
  UINTN  i;

  if (gST == NULL) {
    return;
  }
  mCfgCount = gST->NumberOfTableEntries;
  mFdtFound = 0;
  mFdtAddr  = 0;
  mFdtSize  = 0;

  for (i = 0; i < gST->NumberOfTableEntries; i++) {
    if (CompareGuid (&gST->ConfigurationTable[i].VendorGuid, &mFdtTableGuid)) {
      UINT8  *F = (UINT8 *) gST->ConfigurationTable[i].VendorTable;
      if (F != NULL) {
        mFdtAddr  = (UINTN) F;
        mFdtSize  = ((UINT32) F[4] << 24) | ((UINT32) F[5] << 16) |
                    ((UINT32) F[6] << 8) | (UINT32) F[7];
        mFdtFound = 2;      /* 2 = 按 GUID 命中 */
        return;
      }
    }
  }

  for (i = 0; i < gST->NumberOfTableEntries; i++) {
    UINT8   *F = (UINT8 *) gST->ConfigurationTable[i].VendorTable;
    UINT32   M;
    if (F == NULL) {
      continue;
    }
    M = ((UINT32) F[0] << 24) | ((UINT32) F[1] << 16) |
        ((UINT32) F[2] << 8)  | (UINT32) F[3];
    if (M == 0xD00DFEEDUL) {
      mFdtAddr  = (UINTN) F;
      mFdtSize  = ((UINT32) F[4] << 24) | ((UINT32) F[5] << 16) |
                  ((UINT32) F[6] << 8) | (UINT32) F[7];
      mFdtFound = 1;        /* 1 = 按魔数命中 */
      return;
    }
  }
}

'''
s = s[:idx] + func + s[idx:]

# 2) ProbeEntry 里的内联扫描 -> 调用函数
start = s.find("  mCfgCount = gST->NumberOfTableEntries;\n\n  /* 找设备树: 不依赖 GUID")
end = s.find("  Status = gBS->LocateProtocol (&gEfiGraphicsOutputProtocolGuid", start)
if start < 0 or end < 0:
    print("找不到 ProbeEntry 里的扫描块")
    sys.exit(1)
s = s[:start] + "  FindFdt ();\n\n" + s[end:]

# 3) OnTextOut 里，刷新 GOP 之后再扫一次
old = "  RefreshGop ();     /* 入口时 FrameBufferBase 可能是 0, 这里重读 */"
new = ("  RefreshGop ();     /* 入口时 FrameBufferBase 可能是 0, 这里重读 */\n"
       "  FindFdt ();        /* 配置表到这时才齐, 重新找一次设备树 */")
if old not in s:
    print("找不到 RefreshGop 调用点")
    sys.exit(1)
s = s.replace(old, new)

# 4) FOUND 显示改成三态
s = s.replace('DrawString (40, yy, mFdtFound ? "FOUND 1" : "FOUND 0", 0xFFFFFFFF);',
              'DrawString (40, yy, mFdtFound == 2 ? "BY GUID" : (mFdtFound == 1 ? "BY MAGIC" : "NOT FOUND"), 0xFFFFFFFF);')

s = s.replace("[fuxi-probe v35]", "[fuxi-probe v36]").replace('L"v35 st=%r fb=%Lx', 'L"v36 st=%r fb=%Lx')

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("已抽出 FindFdt()，并在退出前重新扫描")
for ln, line in enumerate(s.split("\n"), 1):
    if any(k in line for k in ("FindFdt", "BY GUID", "v36 st=")):
        print("  L%d: %s" % (ln, line.strip()[:80]))
