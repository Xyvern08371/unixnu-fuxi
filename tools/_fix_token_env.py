import io
import yaml

p = r"E:\ios-on-fuxi\.github\workflows\build-xnu-macos.yml"
t = io.open(p, encoding="utf-8").read()

old = """      - name: 给 prepare-xnu-source.py 加 API token
        if: ${{ !env.SKIP_TOKEN_PATCH }}
        run: |"""

new = """      - name: 给 prepare-xnu-source.py 加 API token
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |"""

if old in t:
    t = t.replace(old, new, 1)
    io.open(p, "w", encoding="utf-8", newline="\n").write(t)
    print("已改为显式传 GITHUB_TOKEN")
elif "GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}" in t:
    print("已经是显式 GITHUB_TOKEN")
else:
    print("锚点没找到，检查当前内容：")
    i = t.find("加 API token")
    print(t[max(0, i - 100):i + 200])

d = yaml.safe_load(io.open(p, encoding="utf-8"))
print("YAML 有效，steps:")
for s in d["jobs"]["build"]["steps"]:
    print("  -", s.get("name", s.get("uses", "?")))
