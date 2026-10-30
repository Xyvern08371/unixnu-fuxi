import io

P = r"E:\ios-on-fuxi\.github\workflows\build-fuxi-uefi.yml"
lines = io.open(P, encoding="utf-8").read().split("\n")

# 找到新加的 fi（紧跟 KERNEL=$(find /tmp/k ...) 那行之后的 fi），删除其后的 4 行残留
idx = None
for i, l in enumerate(lines):
    if l.strip() == "fi" and "KERNEL=$(find /tmp/k" in lines[i - 1]:
        idx = i
        break

if idx is None:
    raise SystemExit("找不到结束 fi")

remove = []
for j in range(idx + 1, min(idx + 6, len(lines))):
    s = lines[j].strip()
    if s.startswith("ls -l /tmp/k.zip") or s.startswith("rm -rf /tmp/k") or \
       s.startswith("unzip -oq /tmp/k.zip") or s.startswith("KERNEL=$(find /tmp/k"):
        remove.append(j)
    elif s.startswith('echo "kernel:'):
        break

print("将删除行号:", [r + 1 for r in remove])
for r in reversed(remove):
    del lines[r]

io.open(P, "w", encoding="utf-8", newline="\n").write("\n".join(lines))

# 自检
t = io.open(P, encoding="utf-8").read()
ls = t.split("\n")
bad = [i for i, l in enumerate(ls, 1) if not l.strip().startswith("#") and l.count('"') % 2]
print("引号不配对:", bad[:5] if bad else "无")

i = next(i for i, l in enumerate(ls) if 'if [ "$ART" != local ]' in l)
print("=== 结果 ===")
for l in ls[i - 2:i + 12]:
    print("|" + l[:110])
