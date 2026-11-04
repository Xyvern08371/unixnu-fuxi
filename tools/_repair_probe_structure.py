import io
import re

P = r"E:\ios-on-fuxi\loader\Probe.c"
lines = io.open(P, encoding="utf-8").read().split("\n")

# 1) 找到 GUID 声明，并把它后面到下一个独立 "};" 之间的垃圾删掉
gi = next(i for i, l in enumerate(lines) if "mFdtTableGuid" in l)
# GUID 实体占两行（声明 + 内容），之后应当直接是 "};"
body_end = gi + 1
# 找到往后第一个独立 "};"
j = next(k for k in range(body_end + 1, len(lines)) if lines[k].strip() == "};")

print(f"GUID 在 L{gi+1}，垃圾段 L{body_end+2}..L{j+1}（{j - body_end} 行）")
print("垃圾段前 3 行:")
for l in lines[body_end + 1:body_end + 4]:
    print("   ", l.strip()[:80])

# 只在那段里确实是字体行时才删（防御）
seg = lines[body_end + 1:j + 1]
if any("0x" in l and "/*" in l for l in seg):
    new_lines = lines[:body_end + 1] + ["};"] + lines[j + 1:]
    io.open(P, "w", encoding="utf-8", newline="\n").write("\n".join(new_lines))
    print(f"已删除垃圾段并补回 '}};'，文件行数 {len(lines)} -> {len(new_lines)}")
else:
    print("!! 那段看起来不是字体垃圾，未改动")

# 2) 校验
t = io.open(P, encoding="utf-8").read()
ls = t.split("\n")
print()
print("=== GUID 附近 ===")
gi2 = next(i for i, l in enumerate(ls) if "mFdtTableGuid" in l)
for l in ls[gi2:gi2 + 4]:
    print("|" + l)

# CHARSET / FONT
start = next(i for i, l in enumerate(ls) if "FONT[" in l)
end = next(i for i in range(start, len(ls)) if ls[i].strip() == "};")
rows = [l for l in ls[start + 1:end] if l.strip().startswith("{")]
m = re.search(r'CHARSET\[\] = "([^"]*)"', t)
print()
print("CHARSET 长度:", len(m.group(1)) if m else "?")
print("FONT 行数:", len(rows))

# 大括号平衡（粗查）
print("大括号:", t.count("{"), "vs", t.count("}"))
