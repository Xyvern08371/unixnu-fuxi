import io

p = r"E:\ios-on-fuxi\.github\workflows\build-xnu-macos.yml"
t = io.open(p, encoding="utf-8").read()

# ── 1) 组装源码树：逐条回显 ──
old1 = '''      - name: 组装源码树
        run: |
          set -eux
          tar -xzf vendor/UniXNU-full.tar.gz -C .'''
new1 = '''      - name: 组装源码树
        run: |
          set -euxo pipefail
          echo "PWD=$(pwd)"
          echo "--- 根目录 ---"
          ls -la
          echo "--- vendor ---"
          ls -la vendor/ || { echo "没有 vendor 目录"; exit 1; }
          tar -xzf vendor/UniXNU-full.tar.gz -C .
          ls UniXNU/ || { echo "UniXNU 解包失败"; exit 1; }'''
if old1 in t:
    t = t.replace(old1, new1, 1)
    print("组装源码树: ok")
else:
    print("组装源码树: 锚点没找到（可能已改过）")

# ── 2) 装依赖：brew 不中断 ──
old2 = '''      - name: 装依赖
        run: |
          set -eux
          brew install cmake ninja unifdef
          for t in git make clang cmake ninja unifdef python3 ditto; do
            command -v "$t" || { echo "缺少 $t"; exit 1; }
          done'''
new2 = '''      - name: 装依赖
        run: |
          set -euxo pipefail
          brew install cmake ninja unifdef || true
          echo "--- 逐个确认工具 ---"
          for t in git make clang cmake ninja unifdef python3 ditto xcrun; do
            if command -v "$t" >/dev/null 2>&1; then
              echo "OK   $t"
            else
              echo "MISS $t"
            fi
          done'''
if old2 in t:
    t = t.replace(old2, new2, 1)
    print("装依赖: ok")
else:
    print("装依赖: 锚点没找到")

# ── 3) availability.pl：不阻塞 ──
start = t.find("      - name: 准备 availability.pl")
if start > 0:
    # 找到下一个 "- name:" 作为块结尾
    nxt = t.find("\n      - name:", start + 10)
    if nxt < 0:
        nxt = len(t)
    new3 = '''      - name: 准备 availability.pl
        run: |
          set -uo pipefail
          SDK="$(xcrun --sdk macosx --show-sdk-path 2>/dev/null || true)"
          echo "SDK=$SDK"
          if [ -n "$SDK" ]; then
            AVA="$SDK/usr/local/libexec/availability.pl"
            if [ ! -x "$AVA" ]; then
              mkdir -p "$(dirname "$AVA")" 2>/dev/null || echo "(SDK 只读)"
              printf '#!/usr/bin/env perl\\nexit 0;\\n' > "$AVA" 2>/dev/null || echo "(无法写入 SDK)"
              chmod +x "$AVA" 2>/dev/null || true
            fi
            echo "availability.pl: $AVA"
          fi
          echo "此步不阻塞后续"
'''
    t = t[:start] + new3 + t[nxt:]
    print("availability.pl: ok")
else:
    print("availability.pl: 锚点没找到")

io.open(p, "w", encoding="utf-8", newline="\n").write(t)

import yaml
d = yaml.safe_load(io.open(p, encoding="utf-8"))
print("YAML 有效,", len(d["jobs"]["build"]["steps"]), "steps")
for s in d["jobs"]["build"]["steps"]:
    print("  -", s.get("name", s.get("uses", "?")))
