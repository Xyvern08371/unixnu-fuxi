"""重写 build-xnu.yml 的尾部：自动把内核提交回仓库（纯 ASCII，避免编码问题）。"""

import io

P = r"E:\ios-on-fuxi\.github\workflows\build-xnu.yml"
t = io.open(P, encoding="utf-8").read()

# 截到 retention-days: 14 为止
key = "retention-days: 14"
idx = t.find(key)
assert idx != -1, "没找到上传产物块"
head = t[: idx + len(key)] + "\n"

# 确保有 permissions
if "permissions:" not in head:
    head = head.replace("on:\n  push:", "permissions:\n  contents: write\n\non:\n  push:", 1)

step = """
      - name: commit kernel back to repo (firmware build uses same binary)
        if: success()
        run: |
          set -e
          if [ ! -f out/kernel.development.fuxi ]; then
            echo "no kernel artifact, skip"
            exit 0
          fi
          mkdir -p rom/xnu
          cp out/kernel.development.fuxi rom/xnu/kernel.development.fuxi
          git config user.name "xnu-bot"
          git config user.email "xnu-bot@users.noreply.github.com"
          git add rom/xnu/kernel.development.fuxi
          if git diff --cached --quiet; then
            echo "kernel unchanged, skip commit"
          else
            git commit -m "rom/xnu: auto-update kernel $(date -u +%Y-%m-%dT%H:%MZ)"
            git push
            echo "committed; firmware build will follow"
          fi
"""

io.open(P, "w", encoding="utf-8", newline="\n").write(head + step)
print("已重写 build-xnu.yml 尾部（纯 ASCII）")
print("总行数:", len((head + step).split("\n")))
