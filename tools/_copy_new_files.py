import io

P = r"E:\ios-on-fuxi\.github\workflows\build-fuxi-uefi.yml"
t = io.open(P, encoding="utf-8").read()

old = '          cp loader/Probe.c loader/Probe.inf "$probe"/'
new = (
    '          cp loader/Probe.c loader/Probe.inf \\\n'
    '             loader/XnuBoot.c loader/xnu_jump.S loader/xnu_payload.S "$probe"/'
)

assert old in t, "找不到 cp 行"
t = t.replace(old, new)
io.open(P, "w", encoding="utf-8", newline="\n").write(t)
print("已更新探针文件复制列表")

lines = t.split("\n")
i = next(i for i, l in enumerate(lines) if "XnuBoot.c loader/xnu_jump.S" in l)
for l in lines[i - 2:i + 3]:
    print("|" + l)

bad = [j for j, l in enumerate(lines, 1)
       if not l.strip().startswith("#") and l.count('"') % 2]
print("引号不配对:", bad[:5] if bad else "无")
