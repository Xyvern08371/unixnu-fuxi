import io

P = r"E:\ios-on-fuxi\.github\workflows\build-fuxi-uefi.yml"
t = io.open(P, encoding="utf-8").read()

TOKEN = "${{" + " github.token }}"   # 避免被 shell 展开

# ---------- 1) permissions ----------
if "permissions:" not in t:
    t = t.replace(
        "jobs:\n",
        "permissions:\n  contents: read\n  actions: read   # 读其它 workflow 的产物\n\njobs:\n",
        1,
    )
    print("已加 permissions")

# ---------- 2) API 失败时的兜底 ----------
old = ('          if [ -z "$ART" ]; then echo "没有 xnu-kernel 产物，跳过 XNU 嵌入"; '
       'cp xnu-payload.log ../xnu-payload.log; exit 0; fi')
new = """          if [ -z "$ART" ]; then
            echo "API 拿不到产物（权限不足）"
            if [ -f rom/xnu/kernel.development.fuxi ]; then
              echo "改用仓库里的内核"
              KERNEL=rom/xnu/kernel.development.fuxi
              ART=local
            else
              echo "仓库里也没有内核，跳过"
              cp xnu-payload.log ../xnu-payload.log
              exit 0
            fi
          fi"""
assert old in t, "兜底锚点没找到"
t = t.replace(old, new)
print("已加兜底逻辑")

# ---------- 3) local 时不下载 ----------
old2 = '          curl -sL -H "Authorization: Bearer ' + TOKEN + '" "$ART" -o /tmp/k.zip\n'
new2 = """          if [ "$ART" != local ]; then
            curl -sL -H "Authorization: Bearer """ + TOKEN + """" "$ART" -o /tmp/k.zip
            ls -l /tmp/k.zip
            rm -rf /tmp/k; mkdir -p /tmp/k
            unzip -oq /tmp/k.zip -d /tmp/k || echo "解压失败"
            KERNEL=$(find /tmp/k -type f -name "kernel.*" | head -1)
          fi
"""
assert old2 in t, "下载锚点没找到"
t = t.replace(old2, new2)
print("已改下载逻辑")

io.open(P, "w", encoding="utf-8", newline="\n").write(t)

# 自检
lines = t.split("\n")
bad = [i for i, l in enumerate(lines, 1) if not l.strip().startswith("#") and l.count('"') % 2]
print("引号不配对:", bad[:5] if bad else "无")

i = next(i for i, l in enumerate(lines) if "ART\" = local" in l or "ART\" != local" in l)
print("=== 关键段 ===")
for l in lines[i - 12:i + 12]:
    print("|" + l[:110])
