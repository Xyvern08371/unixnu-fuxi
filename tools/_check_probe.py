import io
import re
import sys

P = r"E:\ios-on-fuxi\loader\Probe.c"
s = io.open(P, encoding="utf-8").read()

# 去掉注释和字符串，做近似括号配对
no_str = re.sub(r'"(?:[^"\\]|\\.)*"', '""', s)
no_com = re.sub(r"/\*.*?\*/", "", no_str, flags=re.S)
no_line = re.sub(r"//[^\n]*", "", no_com)

b1, b2 = no_line.count("{"), no_line.count("}")
p1, p2 = no_line.count("("), no_line.count(")")

print("braces: %d / %d %s" % (b1, b2, "ok" if b1 == b2 else "MISMATCH"))
print("parens: %d / %d %s" % (p1, p2, "ok" if p1 == p2 else "MISMATCH"))

# 检查关键函数的顺序
names = ["Fill", "DrawString", "Hex", "PayloadEntry", "JumpToPayload", "OnTextOut", "ProbeEntry"]
pos = {}
for n in names:
    m = re.search(r"\n" + n + r" \(", s)
    pos[n] = m.start() if m else -1
print("顺序:", pos)

# 检查 PayloadEntry 里有没有调用定义更晚的函数
late = [n for n in ("Fill", "DrawString", "Hex") if pos[n] > pos["PayloadEntry"]]
print("PayloadEntry 之后才定义的依赖:", late if late else "无")

sys.exit(0 if b1 == b2 and p1 == p2 and not late else 1)
