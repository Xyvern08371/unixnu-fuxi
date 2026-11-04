import io
import sys

W = r"E:\ios-on-fuxi\.github\workflows\build-xnu.yml"
lines = io.open(W, encoding="utf-8").read().split("\n")

# ---------- 1) 在 "去掉 -Werror" 之前插入"补老版本工具链"步骤 ----------
anchor = None
for i, l in enumerate(lines):
    if l.strip().startswith("- name:") and "去掉 -Werror" in l:
        anchor = i
        break
if anchor is None:
    print("找不到锚点")
    sys.exit(1)

NEW_STEP = r'''      - name: 补老版本工具链（xnu-6153 时代依赖 cctools 的 CTF 工具）
        if: always()
        run: |
          set +e
          exec > >(tee -a oldtool.log) 2>&1
          set -x
          mkdir -p "$HOME/bin"

          # Xcode 15 已经没有 ctfconvert / ctfmerge（CTF 调试信息转换工具）。
          # 我们只要内核镜像，不需要 CTF，所以造两个空壳。
          for t in ctfconvert ctfmerge ctfdump; do
            printf '#!/bin/sh\nexit 0\n' > "$HOME/bin/$t"
            chmod +x "$HOME/bin/$t"
          done
          ls -l "$HOME/bin"
          echo "$HOME/bin" >> "$GITHUB_PATH"

          # 老 Makefile 靠这些变量拼 -arch，空值会变成 "-arch -mmacosx-version-min=..."
          echo "RC_ARCHS=arm64" >> "$GITHUB_ENV"
          echo "ARCHS=arm64" >> "$GITHUB_ENV"
          echo "KERNEL_ARCHS=arm64" >> "$GITHUB_ENV"

          echo "=== PATH 现在有 ==="
          echo "$PATH"
          echo "=== 试试 ctfconvert ==="
          "$HOME/bin/ctfconvert" --version; echo "退出码 $?"
'''

lines[anchor:anchor] = NEW_STEP.split("\n")
io.open(W, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
print(f"已在行 {anchor+1} 前插入补工具链步骤")

# ---------- 2) 构建步骤的 MAKE 加上 ARCHS/RC_ARCHS ----------
text = io.open(W, encoding="utf-8").read()
old_make = 'MAKE="make -j$NCPU ARCH_CONFIGS=ARM64 KERNEL_CONFIGS=RELEASE"'
new_make = 'MAKE="make -j$NCPU ARCH_CONFIGS=ARM64 KERNEL_CONFIGS=RELEASE ARCHS=arm64 RC_ARCHS=arm64"'
if old_make in text:
    text = text.replace(old_make, new_make)
    print("已给 make 加上 ARCHS/RC_ARCHS")
else:
    print("!! 没找到 MAKE 定义")

# ---------- 3) 打印 -db 错误的上下文 ----------
old_dbg = '''          tail -25 pass3.log'''
new_dbg = '''          tail -25 pass3.log
          echo "=== -db / Command not found 的上下文 ==="
          grep -n -B3 -A3 "Command not found" pass3.log 2>/dev/null | head -30 || true'''
if old_dbg in text:
    text = text.replace(old_dbg, new_dbg)
    print("已加 -db 上下文打印")

io.open(W, "w", encoding="utf-8", newline="\n").write(text)

# 产物里加 oldtool.log
text = io.open(W, encoding="utf-8").read()
if "            oldtool.log" not in text:
    text = text.replace("            env.log", "            env.log\n            oldtool.log")
    io.open(W, "w", encoding="utf-8", newline="\n").write(text)
    print("已加入 oldtool.log 到产物")

lines2 = io.open(W, encoding="utf-8").read().split("\n")
bad = [i for i, l in enumerate(lines2, 1)
       if not l.strip().startswith("#") and l.count('"') % 2]
print("引号不配对:", bad[:5] if bad else "无")
