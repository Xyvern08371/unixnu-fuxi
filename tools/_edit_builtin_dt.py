import io
import sys

P = r"E:\ios-on-fuxi\loader\Probe.c"
s = io.open(P, encoding="utf-8").read()

# 1) 外部声明（内嵌设备树）
anchor = "/** 在 EFI 配置表里找设备树"
idx = s.find(anchor)
if idx < 0:
    print("找不到 FindFdt 注释锚点")
    sys.exit(1)
decl = '''/* 由 tools/gen_dtb_blob.py 从 rom/device/fuxi_runtime.dtb 生成 */
extern CONST UINT8   gFuxiDtbData[];
extern CONST UINT32  gFuxiDtbSize;

'''
s = s[:idx] + decl + s[idx:]

# 2) FindFdt 末尾加"用内嵌设备树"兜底
old_tail = '''    if (M == 0xD00DFEEDUL) {
      mFdtAddr  = (UINTN) F;
      mFdtSize  = ((UINT32) F[4] << 24) | ((UINT32) F[5] << 16) |
                  ((UINT32) F[6] << 8) | (UINT32) F[7];
      mFdtFound = 1;        /* 1 = 按魔数命中 */
      return;
    }
  }
}'''
new_tail = '''    if (M == 0xD00DFEEDUL) {
      mFdtAddr  = (UINTN) F;
      mFdtSize  = ((UINT32) F[4] << 24) | ((UINT32) F[5] << 16) |
                  ((UINT32) F[6] << 8) | (UINT32) F[7];
      mFdtFound = 1;        /* 1 = 按魔数命中 */
      return;
    }
  }

  /* 配置表里没有: 用编进本驱动的设备树
     (实测这版固件不把 DT 放进配置表) */
  if (gFuxiDtbSize > 0) {
    mFdtAddr  = (UINTN) gFuxiDtbData;
    mFdtSize  = (UINT32) gFuxiDtbSize;
    mFdtFound = 3;          /* 3 = 内嵌副本 */
  }
}'''
if old_tail not in s:
    print("找不到 FindFdt 结尾")
    sys.exit(1)
s = s.replace(old_tail, new_tail)

# 3) payload 的 FOUND 显示加 BUILTIN
s = s.replace(
    'DrawString (40, yy, mFdtFound == 2 ? "BY GUID" : (mFdtFound == 1 ? "BY MAGIC" : "NOT FOUND"), 0xFFFFFFFF);',
    'DrawString (40, yy, mFdtFound == 2 ? "BY GUID" : (mFdtFound == 1 ? "BY MAGIC" : (mFdtFound == 3 ? "BUILTIN" : "NOT FOUND")), 0xFFFFFFFF);'
)

s = s.replace("[fuxi-probe v36]", "[fuxi-probe v37]").replace('L"v36 st=%r fb=%Lx', 'L"v37 st=%r fb=%Lx')

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("已加入内嵌设备树兜底")

for ln, line in enumerate(s.split("\n"), 1):
    if any(k in line for k in ("gFuxiDtb", "BUILTIN", "v37 st=")):
        print("  L%d: %s" % (ln, line.strip()[:88]))
