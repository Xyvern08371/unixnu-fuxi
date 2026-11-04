import io
import sys

P = r"E:\ios-on-fuxi\.github\workflows\build-xnu.yml"
lines = io.open(P, encoding="utf-8").read().split("\n")

# 在 "打包产物" 之前插入分析步骤
anchor = None
for i, l in enumerate(lines):
    if l.strip().startswith("- name:") and "打包产物" in l:
        anchor = i
        break
if anchor is None:
    print("找不到打包步骤")
    sys.exit(1)

NEW = r'''      - name: 分析未定义符号（定位是哪些文件没参与编译）
        if: always()
        run: |
          exec > >(tee -a undef.log) 2>&1
          set -x
          python3 "$GITHUB_WORKSPACE/tools/analyze_undef.py" build.log xnu 2>&1 | head -120

'''

lines[anchor:anchor] = NEW.split("\n")
io.open(P, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
print(f"已在行 {anchor+1} 前插入分析步骤")

text = io.open(P, encoding="utf-8").read()
if "            undef.log" not in text:
    text = text.replace("            startup.log", "            startup.log\n            undef.log")
    io.open(P, "w", encoding="utf-8", newline="\n").write(text)
    print("已把 undef.log 加入产物")

lines2 = io.open(P, encoding="utf-8").read().split("\n")
bad = [i for i, l in enumerate(lines2, 1) if not l.strip().startswith("#") and l.count('"') % 2]
print("引号不配对:", bad[:5] if bad else "无")
