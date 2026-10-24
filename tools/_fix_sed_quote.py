import io

P = r"E:\ios-on-fuxi\.github\workflows\build-xnu.yml"
lines = io.open(P, encoding="utf-8").read().split("\n")

out = []
i = 0
fixed = 0
while i < len(lines):
    l = lines[i]
    if 'sed -i "" "1i' in l:
        indent = len(l) - len(l.lstrip())
        out.append(" " * indent + 'sed -i \'\' "1i #include <arm64/fuxi_decls.h>" "$REL"')
        fixed += 1
        i += 1
        # 跳过残留的 #include 行和单独的双引号行
        while i < len(lines) and not lines[i].strip().startswith("echo"):
            i += 1
        continue
    out.append(l)
    i += 1

io.open(P, "w", encoding="utf-8", newline="\n").write("\n".join(out))
print(f"修复了 {fixed} 处 sed 多行插入")

lines2 = io.open(P, encoding="utf-8").read().split("\n")
bad = [i for i, l in enumerate(lines2, 1)
       if not l.strip().startswith("#") and l.count('"') % 2]
print("引号不配对行:", bad[:5] if bad else "无")

# 打印注入段
for i, l in enumerate(lines2):
    if "fuxi_decls.h>" in l:
        for x in lines2[max(0, i - 8):i + 4]:
            print("|" + x)
        break
