import io
import sys

P = r"E:\ios-on-fuxi\loader\Probe.c"
s = io.open(P, encoding="utf-8").read()

# 1) 在 ProbeEntry 里，用"扫描魔数"的方式找设备树（不再依赖 GUID）
old_lookup = '''  for (i = 0; i < gST->NumberOfTableEntries; i++) {
    if (CompareGuid (&gST->ConfigurationTable[i].VendorGuid, &mFdtTableGuid)) {
      UINT8  *F = (UINT8 *) gST->ConfigurationTable[i].VendorTable;
      mFdtAddr = (UINTN) F;
      if (F != NULL) {
        mFdtSize = ((UINT32) F[4] << 24) | ((UINT32) F[5] << 16) |
                   ((UINT32) F[6] << 8) | (UINT32) F[7];
      }
      break;
    }
  }
'''
new_lookup = '''  /* 找设备树: 不依赖 GUID —— 直接看哪一块配置表数据的开头是 DTB 魔数。
     (实测这版固件没有按 b1b621d5-... 发布, 所以按 GUID 找不到) */
  for (i = 0; i < gST->NumberOfTableEntries; i++) {
    UINT8   *F = (UINT8 *) gST->ConfigurationTable[i].VendorTable;
    UINT32   M = 0;
    if (F == NULL) {
      continue;
    }
    M = ((UINT32) F[0] << 24) | ((UINT32) F[1] << 16) |
        ((UINT32) F[2] << 8)  | (UINT32) F[3];
    if (M == 0xD00DFEEDUL) {
      mFdtAddr = (UINTN) F;
      mFdtSize = ((UINT32) F[4] << 24) | ((UINT32) F[5] << 16) |
                 ((UINT32) F[6] << 8) | (UINT32) F[7];
      mFdtFound = 1;
      break;
    }
  }
'''
if old_lookup not in s:
    print("未匹配原来的 GUID 查找代码")
    sys.exit(1)
s = s.replace(old_lookup, new_lookup)

# 2) 加一个"是否找到"的全局
s = s.replace("STATIC UINTN       mKernelStack;",
              "STATIC UINTN       mKernelStack;\nSTATIC UINT32      mFdtFound;")

# 3) payload 里显示是否找到
old_draw = '''  DrawString (40, yy, Magic == 0xD00DFEEDUL ? "DT OK" : "DT BAD", 0xFFFFFFFF);'''
new_draw = '''  DrawString (40, yy, Magic == 0xD00DFEEDUL ? "DT OK" : "DT BAD", 0xFFFFFFFF);
  yy += LINE_H;

  DrawString (40, yy, mFdtFound ? "FOUND 1" : "FOUND 0", 0xFFFFFFFF);
  yy += LINE_H;

  DrawString (40, yy, "CFG", 0xFFFFFFFF);
  Hex ((UINT64) mCfgCount, Num);
  DrawString (40 + 3 * 8 * SCALE, yy, Num, 0xFFFFFFFF);'''
if old_draw not in s:
    print("未匹配 payload 绘制行")
    sys.exit(1)
s = s.replace(old_draw, new_draw)

# 4) 记录配置表数量
s = s.replace("STATIC UINT32      mFdtFound;",
              "STATIC UINT32      mFdtFound;\nSTATIC UINTN       mCfgCount;")
s = s.replace("  /* 找设备树: 不依赖 GUID",
              "  mCfgCount = gST->NumberOfTableEntries;\n\n  /* 找设备树: 不依赖 GUID")

s = s.replace("[fuxi-probe v34]", "[fuxi-probe v35]").replace('L"v34 st=%r fb=%Lx', 'L"v35 st=%r fb=%Lx')

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("已改为按魔数扫描")
for ln, line in enumerate(s.split("\n"), 1):
    if any(k in line for k in ("mFdtFound", "mCfgCount", "v35 st=")):
        print("  L%d: %s" % (ln, line.strip()[:88]))
