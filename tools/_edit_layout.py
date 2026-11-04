import io
import sys

P = r"E:\ios-on-fuxi\loader\Probe.c"
s = io.open(P, encoding="utf-8").read()

start = s.find("  Fill (0xFF000000);\n\n  yy = 120;")
end = s.find("  /* 缓存回扫: 把像素挤到显存 */")
if start < 0 or end < 0:
    print("找不到 payload 绘制段")
    sys.exit(1)

new = r'''  Fill (0xFF000000);

  yy = 100;

  /* 每个数字单独一行, 避免超出 1080 宽度 */
  DrawString (40, yy, "M4", 0xFFFFFFFF);
  yy += LINE_H;

  DrawString (40, yy, "DTB", 0xFFFFFFFF);
  yy += LINE_H;
  Hex (Dtb, Num);
  DrawString (40, yy, Num, 0xFFFFFFFF);
  yy += LINE_H;

  DrawString (40, yy, "MAGIC", 0xFFFFFFFF);
  yy += LINE_H;
  Hex ((UINT64) Magic, Num);
  DrawString (40, yy, Num, 0xFFFFFFFF);
  yy += LINE_H;

  DrawString (40, yy, Magic == 0xD00DFEEDUL ? "DT OK" : "DT BAD", 0xFFFFFFFF);
  yy += LINE_H;

  DrawString (40, yy, mFdtFound ? "FOUND 1" : "FOUND 0", 0xFFFFFFFF);
  yy += LINE_H;

  DrawString (40, yy, "CFG", 0xFFFFFFFF);
  yy += LINE_H;
  Hex ((UINT64) mCfgCount, Num);
  DrawString (40, yy, Num, 0xFFFFFFFF);
  yy += LINE_H;

'''
s = s[:start] + new + s[end:]
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("已重排 payload 绘制（数字独立成行）")

for ln, line in enumerate(s.split("\n"), 1):
    if "DrawString (40, yy," in line or "Hex (" in line:
        print("  L%d: %s" % (ln, line.strip()[:70]))
