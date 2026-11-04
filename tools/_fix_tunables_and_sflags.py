import io
import sys

P = r"E:\ios-on-fuxi\.github\workflows\build-xnu.yml"
text = io.open(P, encoding="utf-8").read()

# 1) tunables.s 占位内容加上 APPLY_TUNABLES 空宏
old_stub = '''            printf "/* fuxi: placeholder for Apple private tunables. Empty on purpose. */\\n" > osfmk/arm64/tunables/tunables.s'''
new_stub = '''            cat > osfmk/arm64/tunables/tunables.s <<'FUXI_TUNE_EOF'
          /*
           * fuxi: 替身文件。
           * 真正的 tunables.s 是 Apple 私有文件（按 SoC 做性能调优），开源树里没有。
           * start.s 里唯一用到的是 APPLY_TUNABLES 宏，这里定义成空操作。
           */
          .macro APPLY_TUNABLES
          .endm
          FUXI_TUNE_EOF'''
# heredoc 会破坏 YAML 块，改用 printf 多行
new_stub = '''            printf "/* fuxi: placeholder for Apple private tunables */\\n" > osfmk/arm64/tunables/tunables.s
            printf ".macro APPLY_TUNABLES\\n.endm\\n" >> osfmk/arm64/tunables/tunables.s'''
if old_stub not in text:
    print("找不到 printf 占位行，改用整段替换")
else:
    text = text.replace(old_stub, new_stub)

# 2) 手工汇编时带上 .SFLAGS
old_clang = '''          clang -c -o "$OBJ/osfmk/arm64/start.o" osfmk/arm64/start.s $INCS \\
            -DARM64=1 -DKERNEL=1 -DPRIVATE=1 -DXNU_TARGET_OS_OSX=1 2>&1 | head -30 || true'''
new_clang = '''          SFLAGS_FILE="$OBJ/osfmk/RELEASE/.SFLAGS"
          if [ -f "$SFLAGS_FILE" ]; then
            echo "=== .SFLAGS 前 20 行 ==="
            head -20 "$SFLAGS_FILE"
            SFLAGS="$(cat "$SFLAGS_FILE")"
          else
            SFLAGS="-DARM64=1 -DKERNEL=1 -DPRIVATE=1 -DXNU_TARGET_OS_OSX=1"
          fi
          clang -c -o "$OBJ/osfmk/arm64/start.o" osfmk/arm64/start.s $INCS $SFLAGS 2>&1 | head -30 || true'''
if old_clang not in text:
    print("找不到 clang 汇编行，需要人工处理")
else:
    text = text.replace(old_clang, new_clang)

io.open(P, "w", encoding="utf-8", newline="\n").write(text)

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
print("APPLY_TUNABLES 出现:", sum("APPLY_TUNABLES" in l for l in lines2))
print(".SFLAGS 出现:", sum(".SFLAGS" in l for l in lines2))
