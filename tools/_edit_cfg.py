import io
import sys

P = r"E:\ios-on-fuxi\loader\Probe.c"
s = io.open(P, encoding="utf-8").read()

# 在打印诊断行之后、取内存图之前，插入配置表枚举
anchor = "  /* ---- 内存图审计 + 正确顺序的 ExitBootServices ----"
idx = s.find(anchor)
if idx < 0:
    print("找不到审计段锚点")
    sys.exit(1)

dump = r'''  /* ---- 枚举 EFI 配置表: 设备树到底挂在哪个 GUID 下 ---- */
  {
    UINTN  ci;
    UINTN  shown = 0;

    UnicodeSPrint (Buf, sizeof (Buf), L"cfg count=%Lu\r\n",
                   (UINT64) gST->NumberOfTableEntries);
    gST->ConOut->OutputString (gST->ConOut, Buf);

    for (ci = 0; ci < gST->NumberOfTableEntries && shown < 12; ci++) {
      UnicodeSPrint (Buf, sizeof (Buf), L"[%Lu] %g ptr=0x%Lx\r\n",
                     (UINT64) ci,
                     &gST->ConfigurationTable[ci].VendorGuid,
                     (UINT64) (UINTN) gST->ConfigurationTable[ci].VendorTable);
      gST->ConOut->OutputString (gST->ConOut, Buf);
      shown++;
    }
  }

'''
s = s[:idx] + dump + s[idx:]

s = s.replace("[fuxi-probe v33]", "[fuxi-probe v34]").replace('L"v33 st=%r fb=%Lx', 'L"v34 st=%r fb=%Lx')

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("已插入配置表枚举")

for ln, line in enumerate(s.split("\n"), 1):
    if "cfg count=" in line or "v34 st=" in line:
        print("  L%d: %s" % (ln, line.strip()[:80]))
