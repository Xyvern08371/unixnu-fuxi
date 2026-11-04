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

NEW = r'''      - name: 构建 XNU（缺件自动补齐 → 空实现 → 链接）
        if: always()
        run: |
          set +e
          set -x
          cd xnu
          NCPU=$(sysctl -n hw.ncpu)
          MAKE="make -j$NCPU ARCH_CONFIGS=ARM64 KERNEL_CONFIGS=RELEASE"

          echo "########## pass 1 ##########"
          $MAKE > pass1.log 2>&1
          tail -15 pass1.log

          # ---- 注释 Apple 私有系统寄存器 ----
          ASM=osfmk/arm64/machine_routines_asm.s
          grep -oE "machine_routines_asm\.s:[0-9]+" pass1.log 2>/dev/null | cut -d: -f2 | sort -un > /tmp/spr.txt
          echo "SPR 行号: $(tr '\n' ' ' < /tmp/spr.txt)"
          while read -r ln; do
            if [ -n "$ln" ]; then
              sed -n "${ln}p" "$ASM"
              sed -i "" "${ln}s|^|// fuxi: apple SPR not on snapdragon |" "$ASM"
            fi
          done < /tmp/spr.txt

          # ---- 编译循环：缺头文件就补空头，最多 8 次 ----
          echo "########## 编译循环（自动补缺失头文件） ##########"
          i=0
          while [ "$i" -lt 8 ]; do
            i=$((i + 1))
            echo "--- 第 $i 轮 ---"
            $MAKE > pass3.log 2>&1
            MISS=$(grep -oE "fatal error: '[^']+' file not found" pass3.log | head -1 | sed "s/.*'\(.*\)'.*/\1/")
            if [ -z "$MISS" ]; then
              echo "没有缺头文件错误了"
              break
            fi
            echo "缺: $MISS"
            case "$MISS" in
              arm64/*|arm/*|kern/*|vm/*|mach/*|machine/*|ppl/*) TARGET="osfmk/$MISS" ;;
              sys/*|net/*|vfs/*|dev/*|kern/*) TARGET="bsd/$MISS" ;;
              libkern/*) TARGET="libkern/$MISS" ;;
              *) TARGET="osfmk/$MISS" ;;
            esac
            mkdir -p "$(dirname "$TARGET")"
            if [ ! -f "$TARGET" ]; then
              printf "/* fuxi: 空头文件，替代缺失的 %s */\n#ifndef FUXI_STUB_%s\n#define FUXI_STUB_%s\n#endif\n" \
                "$MISS" "$(echo "$MISS" | tr '/.' '__')" "$(echo "$MISS" | tr '/.' '__')" > "$TARGET"
              echo "已创建: $TARGET"
            else
              echo "文件已存在却仍找不到（include 路径问题），停止: $TARGET"
              break
            fi
          done
          tail -25 pass3.log

          # ---- 未定义符号 → 空实现 ----
          echo "########## 生成空实现 ##########"
          python3 "$GITHUB_WORKSPACE/tools/gen_stubs.py" pass3.log osfmk/arm64/fuxi_stubs.c
          head -15 osfmk/arm64/fuxi_stubs.c 2>/dev/null
          if ! grep -q "osfmk/arm64/fuxi_stubs.c" osfmk/conf/files.arm64; then
            printf "osfmk/arm64/fuxi_stubs.c\tstandard\n" >> osfmk/conf/files.arm64
            echo "已加入 files.arm64"
          fi

          # ---- 最终链接 ----
          echo "########## 最终链接 ##########"
          $MAKE > pass4.log 2>&1
          tail -45 pass4.log

          echo "########## 产出物 ##########"
          ls -lh BUILD/obj/RELEASE_ARM64_VMAPPLE/kernel* 2>/dev/null || echo "还没有 kernel"
          find BUILD -name "kernel.release*" -type f | head -5

          cat pass1.log pass3.log pass4.log > build.log
          cp -f pass1.log pass3.log pass4.log build.log .. 2>/dev/null || true
'''

lines[start:end] = NEW.split("\n")
io.open(W, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
print(f"已替换构建步骤（原行 {start+1}..{end}）")

text = io.open(W, encoding="utf-8").read()
if "            pass4.log" not in text:
    text = text.replace("            pass3.log", "            pass3.log\n            pass4.log")
    io.open(W, "w", encoding="utf-8", newline="\n").write(text)
    print("已加入 pass4.log 到产物")

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
print("循环 depth:", d, "(while 不参与此计数)")
