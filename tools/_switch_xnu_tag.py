import io
import sys

W = r"E:\ios-on-fuxi\.github\workflows\build-xnu.yml"
lines = io.open(W, encoding="utf-8").read().split("\n")

# 1) fetch 步骤：加版本变量 + 回退列表
start = None
for i, l in enumerate(lines):
    if l.strip().startswith("- name:") and "取 XNU 源码" in l:
        start = i
        break
if start is None:
    print("找不到 fetch 步骤")
    sys.exit(1)

end = start + 1
while end < len(lines):
    t = lines[end].strip()
    if t.startswith("- name:") or t.startswith("- uses:"):
        break
    end += 1

NEW = r'''      - name: 取 XNU 源码（可切换版本）
        if: always()
        run: |
          set +e
          exec > >(tee -a fetch.log) 2>&1
          set -x
          # 版本选择：
          #   xnu-6153 = iOS 13 / macOS 10.15，没有 PPL、没有 SART/UAT
          #   xnu-8792 = iOS 16，pmap 深度绑定 Apple 私有安全层（PPL/SART）
          # 我们要的是"能跑在非 Apple 硬件上"，所以选老的。
          for TAG in xnu-6153.11.26 xnu-6153.141.1 xnu-4903.221.2; do
            echo "尝试 clone $TAG"
            if git clone --depth 1 --branch "$TAG" https://github.com/apple-oss-distributions/xnu.git xnu 2>&1; then
              echo "OK: $TAG"
              echo "$TAG" > ../xnu-tag.txt
              break
            fi
            rm -rf xnu
          done
          cd xnu
          git log --oneline -1
          echo "=== 版本确认 ==="
          cat ../xnu-tag.txt 2>/dev/null || echo "(未记录)"
          echo "=== 有没有 PPL/SART（iOS16 特征）==="
          ls osfmk/arm64/ppl 2>/dev/null | head -5 || echo "(没有 ppl 目录 = 好)"
          find . -name "sart*" 2>/dev/null | head -5 || true
'''

lines[start:end] = NEW.split("\n")
io.open(W, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
print(f"已替换 fetch 步骤（原行 {start+1}..{end}）")

# 2) 产物里加 xnu-tag.txt
text = io.open(W, encoding="utf-8").read()
if "            xnu-tag.txt" not in text:
    text = text.replace("            env.log", "            env.log\n            xnu-tag.txt")
    io.open(W, "w", encoding="utf-8", newline="\n").write(text)
    print("已加入 xnu-tag.txt 到产物")

# 自检
lines2 = io.open(W, encoding="utf-8").read().split("\n")
bad = [i for i, l in enumerate(lines2, 1)
       if not l.strip().startswith("#") and l.count('"') % 2]
print("引号不配对:", bad[:5] if bad else "无")
