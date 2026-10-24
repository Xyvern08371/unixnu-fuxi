import io
import sys

# ---------- 1) patch 脚本：从 nos_arm_asm 扩展为所有 nos_* 门控 ----------
P = r"E:\ios-on-fuxi\xnu-stubs\patch_files_arm64.py"
s = io.open(P, encoding="utf-8").read()

old_cond = '''        # 放开所有带 nos_arm_asm 的条目（只限源文件真实存在的）
        if "nos_arm_asm" not in line:
            continue'''
new_cond = '''        # 放开所有带 nos_* 门控的条目（nos_arm_asm / nos_arm_pmap 等），
        # 前提是源文件在开源树里真实存在。
        if "nos_" not in line:
            continue'''
if old_cond in s:
    s = s.replace(old_cond, new_cond)
    io.open(P, "w", encoding="utf-8", newline="\n").write(s)
    print("patch 脚本：已扩展为所有 nos_* 门控")
else:
    print("!! patch 脚本条件未匹配")

# ---------- 2) 工作流：三段式（pass1 → 修 SPR → pass2 → 生成空实现 → pass3） ----------
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

NEW = r'''      - name: 构建 XNU（三段式：修 SPR → 补空实现 → 链接）
        if: always()
        run: |
          set +e
          set -x
          cd xnu
          NCPU=$(sysctl -n hw.ncpu)
          MAKE="make -j$NCPU ARCH_CONFIGS=ARM64 KERNEL_CONFIGS=RELEASE"

          echo "########## pass 1 ##########"
          $MAKE > pass1.log 2>&1
          tail -20 pass1.log

          # --- 注释 Apple 私有系统寄存器（clang 不认）---
          ASM=osfmk/arm64/machine_routines_asm.s
          grep -oE "machine_routines_asm\.s:[0-9]+" pass1.log 2>/dev/null | cut -d: -f2 | sort -un > /tmp/spr.txt
          echo "SPR 行号: $(tr '\n' ' ' < /tmp/spr.txt)"
          while read -r ln; do
            if [ -n "$ln" ]; then
              sed -n "${ln}p" "$ASM"
              sed -i "" "${ln}s|^|// fuxi: apple SPR not on snapdragon |" "$ASM"
            fi
          done < /tmp/spr.txt

          echo "########## pass 2 ##########"
          $MAKE > pass2.log 2>&1
          tail -20 pass2.log

          # --- 未定义符号 → 空实现 ---
          echo "########## 生成空实现 ##########"
          python3 "$GITHUB_WORKSPACE/tools/gen_stubs.py" pass2.log osfmk/arm64/fuxi_stubs.c
          head -20 osfmk/arm64/fuxi_stubs.c 2>/dev/null

          if ! grep -q "osfmk/arm64/fuxi_stubs.c" osfmk/conf/files.arm64; then
            printf "osfmk/arm64/fuxi_stubs.c\tstandard\n" >> osfmk/conf/files.arm64
            echo "已把 fuxi_stubs.c 加入 files.arm64"
          fi

          echo "########## pass 3 ##########"
          $MAKE > pass3.log 2>&1
          tail -40 pass3.log

          echo "########## 产出物 ##########"
          ls -lh BUILD/obj/RELEASE_ARM64_VMAPPLE/kernel* 2>/dev/null || echo "还没有 kernel"
          find BUILD -name "kernel.release*" -type f | head -5

          cat pass1.log pass2.log pass3.log > build.log
          cp -f pass1.log pass2.log pass3.log build.log .. 2>/dev/null || true
'''

lines[start:end] = NEW.split("\n")
io.open(W, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
print(f"已替换构建步骤（原行 {start+1}..{end}）")

# 3) pass3.log 加入产物
text = io.open(W, encoding="utf-8").read()
if "            pass3.log" not in text:
    text = text.replace("            pass2.log", "            pass2.log\n            pass3.log")
    io.open(W, "w", encoding="utf-8", newline="\n").write(text)
    print("已加入 pass3.log 到产物")

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
print("pass3 出现次数:", sum("pass3" in l for l in lines2))
