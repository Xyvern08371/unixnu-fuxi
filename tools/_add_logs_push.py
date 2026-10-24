import io

p = r"E:\ios-on-fuxi\.github\workflows\build-xnu-macos.yml"
t = io.open(p, encoding="utf-8").read()

# 在「上传日志」步骤之前插入一个步骤：把 step2 日志推到 docs/ci-logs 分支
anchor = """      - name: 上传日志"""

inject = """      # 日志 artifact 下载要认证，这里把失败的 step2 日志直接提交到
      # ci-logs 分支的根目录，用 raw.githubusercontent.com 就能匿名读到。
      - name: 失败日志推到 ci-logs 分支
        if: always()
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          set -uo pipefail
          ls -la step2-*.log 2>/dev/null || { echo "没有 step2 日志"; exit 0; }
          mkdir -p /tmp/logs && cp step2-*.log /tmp/logs/ 2>/dev/null || true
          [ -f UniXNU/step1.log ] && cp UniXNU/step1.log /tmp/logs/ || true
          [ -f step1.log ] && cp step1.log /tmp/logs/ || true
          cd /tmp/logs
          ls -la
          git init -q .
          git config user.name  "ci-bot"
          git config user.email "ci@localhost"
          git add -A
          git commit -q -m "logs run ${{ github.run_number }}" || { echo "无变化"; exit 0; }
          git push -f "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" HEAD:ci-logs 2>&1 | tail -5 || true

      - name: 上传日志"""

if anchor in t and "失败日志推到 ci-logs 分支" not in t:
    t = t.replace(anchor, inject, 1)
    io.open(p, "w", encoding="utf-8", newline="\n").write(t)
    print("已插入 ci-logs 推送步骤")
else:
    print("锚点:", "已存在" if "ci-logs 分支" in t else "找不到")

import yaml
d = yaml.safe_load(io.open(p, encoding="utf-8"))
print("YAML 有效，steps:")
for s in d["jobs"]["build"]["steps"]:
    print("  -", s.get("name", s.get("uses", "?")))
