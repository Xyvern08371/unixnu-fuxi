import io
import sys

P = r"E:\ios-on-fuxi\.github\workflows\build-xnu.yml"
lines = io.open(P, encoding="utf-8").read().split("\n")

# 在 "构建 XNU" 步骤之前插入补文件步骤
anchor = None
for i, l in enumerate(lines):
    if l.strip().startswith("- name:") and "构建 XNU" in l:
        anchor = i
        break
if anchor is None:
    print("找不到构建步骤")
    sys.exit(1)

NEW = r'''      - name: 补上缺失的 tunables.s（Apple 私有文件，开源树里没有）
        run: |
          exec > >(tee -a tunables.log) 2>&1
          set -x
          cd xnu

          echo "=== start.s 里跟 tunables 有关的行 ==="
          grep -n -i "tunables" osfmk/arm64/start.s || echo "(只有 include，正文没用到)"

          echo "=== start.s 里可疑的宏用法（大写 TUNE/TUNABLE 前缀）==="
          grep -n -E "\b(TUNE|TUNABLE)[A-Z_]*" osfmk/arm64/start.s | head -20 || echo "(没有)"

          echo "=== 建一个空的 tunables.s ==="
          mkdir -p osfmk/arm64/tunables
          if [ ! -f osfmk/arm64/tunables/tunables.s ]; then
            printf "/* fuxi: placeholder for Apple private tunables. Empty on purpose. */\n" > osfmk/arm64/tunables/tunables.s
          fi
          ls -l osfmk/arm64/tunables/tunables.s
          cat osfmk/arm64/tunables/tunables.s

'''

lines[anchor:anchor] = NEW.split("\n")
io.open(P, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
print(f"已在行 {anchor+1} 前插入补文件步骤")

# 把 tunables.log 加进产物
text = io.open(P, encoding="utf-8").read()
if "            tunables.log" not in text:
    text = text.replace("            startup.log", "            startup.log\n            tunables.log")
    io.open(P, "w", encoding="utf-8", newline="\n").write(text)
    print("已把 tunables.log 加入产物")

# 自检
lines2 = io.open(P, encoding="utf-8").read().split("\n")
bad = [i for i, l in enumerate(lines2, 1) if not l.strip().startswith("#") and l.count('"') % 2]
print("引号不配对:", bad[:5] if bad else "无")
d = 0
for l in lines2:
    s = l.strip()
    if s.startswith("for ") and s.endswith("; do"):
        d += 1
    elif s == "done":
        d -= 1
print("循环 depth:", d)
