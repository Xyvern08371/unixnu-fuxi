import io
import sys
import re

# ---------- 1) patch 脚本：不再排除 machine_routines_asm.s ----------
P = r"E:\ios-on-fuxi\xnu-stubs\patch_files_arm64.py"
s = io.open(P, encoding="utf-8").read()
old = '''        # machine_routines_asm.s 里有 Apple 私有系统寄存器（ACC_OVRD 等），
        # clang 的集成汇编器不认，而且这些寄存器在骁龙上不存在。
        # 先保持排除，看链接器还缺不缺它的符号。
        if src_rel.endswith("machine_routines_asm.s"):
            print(f"跳过（Apple 私有寄存器）: {src_rel}")
            continue
'''
if old in s:
    s = s.replace(old, "")
    io.open(P, "w", encoding="utf-8", newline="\n").write(s)
    print("已移除 machine_routines_asm.s 的排除规则")
else:
    print("!! 没找到排除规则（可能已改）")

# ---------- 2) 工作流：两段式，第一遍失败后自动注释私有寄存器行 ----------
W = r"E:\ios-on-fuxi\.github\workflows\build-xnu.yml"
lines = io.open(W, encoding="utf-8").read().split("\n")

start = None
for i, l in enumerate(lines):
    if l.strip().startswith("- name:") and "构建 XNU" in l:
        start = i
        break
if start is None:
    print("找不到构建步骤")
    sys.exit(1)

end = start + 1
while end < len(lines):
    t = lines[end].strip()
    if t.startswith("- name:") or t.startswith("- uses:"):
        break
    end += 1

NEW = r'''      - name: 构建 XNU（私有寄存器行自动注释后重编）
        run: |
          exec > >(tee -a build.log) 2>&1
          set -x
          cd xnu
          NCPU=$(sysctl -n hw.ncpu)

          echo "=== pass 1 ==="
          make -j"$NCPU" ARCH_CONFIGS=ARM64 KERNEL_CONFIGS=RELEASE || true

          ASM=osfmk/arm64/machine_routines_asm.s
          echo "=== 从错误里提取需要注释的行号 ==="
          grep -oE "machine_routines_asm\.s:[0-9]+" build.log 2>/dev/null | cut -d: -f2 | sort -un > /tmp/spr_lines.txt || true
          cat /tmp/spr_lines.txt 2>/dev/null || echo "(没有)"
          echo "=== 这些行的原文 ==="
          while read -r ln; do
            [ -n "$ln" ] && sed -n "${ln}p" "$ASM"
          done < /tmp/spr_lines.txt
          echo "=== 注释掉它们（Apple 私有系统寄存器，骁龙上不存在）==="
          while read -r ln; do
            if [ -n "$ln" ]; then
              sed -i "" "${ln}s|^|// fuxi: apple SPR not on snapdragon |" "$ASM"
              sed -n "${ln}p" "$ASM"
            fi
          done < /tmp/spr_lines.txt

          echo "=== pass 2 ==="
          make -j"$NCPU" ARCH_CONFIGS=ARM64 KERNEL_CONFIGS=RELEASE || true

          echo "=== 产出物 ==="
          ls -lh BUILD/obj/RELEASE_ARM64_VMAPPLE/kernel* 2>/dev/null || echo "还没有 kernel"
          find BUILD -name "kernel.release*" -type f | head -5
'''

lines[start:end] = NEW.split("\n")
io.open(W, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
print(f"已替换构建步骤（原行 {start+1}..{end}）")

# 自检
lines2 = io.open(W, encoding="utf-8").read().split("\n")
bad = [i for i, l in enumerate(lines2, 1)
       if not l.strip().startswith("#") and l.count('"') % 2]
print("引号不配对:", bad[:5] if bad else "无")
d = 0
for l in lines2:
    t = l.strip()
    if t.startswith("for ") and t.endswith("; do"):
        d += 1
    elif t == "done":
        d -= 1
print("循环 depth:", d)
print("sed 里用到的 $ln 出现次数:", sum("$ln" in l for l in lines2))
