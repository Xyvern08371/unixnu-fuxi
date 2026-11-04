import io
import sys

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
          set -x
          cd xnu
          NCPU=$(sysctl -n hw.ncpu)

          echo "=== pass 1 ==="
          make -j"$NCPU" ARCH_CONFIGS=ARM64 KERNEL_CONFIGS=RELEASE > pass1.log 2>&1 || true
          tail -30 pass1.log

          ASM=osfmk/arm64/machine_routines_asm.s
          echo "=== 从 pass1.log 提取出问题的行号 ==="
          grep -oE "machine_routines_asm\.s:[0-9]+" pass1.log 2>/dev/null | cut -d: -f2 | sort -un > /tmp/spr_lines.txt || true
          echo "行号列表:"; cat /tmp/spr_lines.txt 2>/dev/null || true
          echo "=== 原文 ==="
          while read -r ln; do
            if [ -n "$ln" ]; then sed -n "${ln}p" "$ASM"; fi
          done < /tmp/spr_lines.txt

          echo "=== 注释掉这些行 ==="
          while read -r ln; do
            if [ -n "$ln" ]; then
              sed -i "" "${ln}s|^|// fuxi: apple SPR not on snapdragon |" "$ASM"
              sed -n "${ln}p" "$ASM"
            fi
          done < /tmp/spr_lines.txt

          echo "=== pass 2 ==="
          make -j"$NCPU" ARCH_CONFIGS=ARM64 KERNEL_CONFIGS=RELEASE > pass2.log 2>&1 || true
          tail -40 pass2.log

          echo "=== 产出物 ==="
          ls -lh BUILD/obj/RELEASE_ARM64_VMAPPLE/kernel* 2>/dev/null || echo "还没有 kernel"
          find BUILD -name "kernel.release*" -type f | head -5

          # 把两个 pass 的日志合并成 build.log 供后续步骤使用
          cat pass1.log pass2.log > build.log
'''

lines[start:end] = NEW.split("\n")
io.open(W, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
print(f"已替换构建步骤（原行 {start+1}..{end}）")

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
