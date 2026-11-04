import io
import sys

# ---------- 1) 更新文件清单补丁脚本：放开所有真实存在的 nos_arm_asm 条目 ----------
P = r"E:\ios-on-fuxi\xnu-stubs\patch_files_arm64.py"
s = io.open(P, encoding="utf-8").read()

old_loop = '''    for i, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            continue
        if "start.s" not in line:
            continue

        parts = line.split()
        if not parts:
            continue
        src_rel = parts[0]

        # 只处理 arm64 的 start.s（x86_64 那个本来就是 standard）
        if not src_rel.endswith("arm64/start.s"):
            continue

        if not (root / src_rel).exists():
            print(f"跳过（源码不存在）: {src_rel}")
            continue

        new = f"{src_rel}\\tstandard"'''

new_loop = '''    for i, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            continue
        # 放开所有带 nos_arm_asm 的条目（只限源文件真实存在的）
        if "nos_arm_asm" not in line:
            continue

        parts = line.split()
        if not parts:
            continue
        src_rel = parts[0]

        if not (root / src_rel).exists():
            print(f"跳过（源码不存在）: {src_rel}")
            continue

        new = f"{src_rel}\\tstandard"'''

if old_loop in s:
    s = s.replace(old_loop, new_loop)
    io.open(P, "w", encoding="utf-8", newline="\n").write(s)
    print("已更新 patch_files_arm64.py：放开所有存在的 nos_arm_asm 条目")
else:
    print("!! patch 脚本结构已变，未修改（需人工确认）")

# ---------- 2) 从工作流里删掉手工汇编那段 ----------
W = r"E:\ios-on-fuxi\.github\workflows\build-xnu.yml"
lines = io.open(W, encoding="utf-8").read().split("\n")

start = None
for i, l in enumerate(lines):
    if "=== 手工汇编 start.o ===" in l:
        start = i
        break

if start is None:
    print("找不到手工汇编段（可能已删）")
else:
    # 向后找到 "=== pass 2" 之前的最后一行
    end = start
    for j in range(start, len(lines)):
        if "=== pass 2" in lines[j]:
            end = j
            break
    removed = end - start
    del lines[start:end]
    io.open(W, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
    print(f"已删除手工汇编段 {removed} 行")

# 自检
lines2 = io.open(W, encoding="utf-8").read().split("\n")
bad = [i for i, l in enumerate(lines2, 1) if not l.strip().startswith("#") and l.count('"') % 2]
print("引号不配对:", bad[:5] if bad else "无")
d = 0
for l in lines2:
    t = l.strip()
    if t.startswith("for ") and t.endswith("; do"):
        d += 1
    elif t == "done":
        d -= 1
print("循环 depth:", d)
print("手工汇编段残留:", sum("手工汇编" in l for l in lines2))
