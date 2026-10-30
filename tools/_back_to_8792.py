import io
import re
import sys

W = r"E:\ios-on-fuxi\.github\workflows\build-xnu.yml"
text = io.open(W, encoding="utf-8").read()
lines = text.split("\n")

# ---------- 1) fetch：回 8792 ----------
s = next(i for i, l in enumerate(lines)
         if l.strip().startswith("- name:") and "取 XNU 源码" in l)
e = s + 1
while e < len(lines) and not lines[e].strip().startswith("- "):
    e += 1
NEW_FETCH = r'''      - name: 取 XNU 源码（xnu-8792）
        if: always()
        run: |
          set +e
          exec > >(tee -a fetch.log) 2>&1
          set -x
          # 回到 8792：它的构建系统在现代 Xcode 下能跑通。
          # xnu-6153 时代的构建脚本依赖 Python2 和 cctools 的 mig，现代环境已不兼容。
          # pmap 依赖的 PPL/SART/UAT 用替身声明解决（见后面步骤）。
          git clone --depth 1 --branch xnu-8792.81.2 https://github.com/apple-oss-distributions/xnu.git xnu
          cd xnu
          git log --oneline -1
          echo "=== PPL/SART/UAT 相关的配置开关 ==="
          grep -rn "HAS_PPL\|CONFIG_PPL\|PLP" osfmk/conf/*.arm64 osfmk/conf/MASTER* 2>/dev/null | head -20 || true
          grep -rn "sart\|SART" osfmk/conf/*.arm64 2>/dev/null | head -10 || true
'''
lines[s:e] = NEW_FETCH.split("\n")
io.open(W, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
print("已把 fetch 改回 8792")

# ---------- 2) 删掉 6153 专用的补工具链步骤 ----------
text = io.open(W, encoding="utf-8").read()
lines = text.split("\n")
s = next((i for i, l in enumerate(lines)
          if l.strip().startswith("- name:") and "补老版本工具链" in l), None)
if s is not None:
    e = s + 1
    while e < len(lines) and not lines[e].strip().startswith("- "):
        e += 1
    del lines[s:e]
    io.open(W, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
    print(f"已删除补老工具链步骤（{e-s} 行）")
else:
    print("没有补工具链步骤")

# ---------- 3) 构建步骤：加 -Wno-implicit-function-declaration + PPL 诊断 ----------
text = io.open(W, encoding="utf-8").read()
lines = text.split("\n")
s = next(i for i, l in enumerate(lines)
         if l.strip().startswith("- name:") and "构建 XNU" in l)
e = s + 1
while e < len(lines) and not lines[e].strip().startswith("- "):
    e += 1

NEW_BUILD = r'''      - name: 构建 XNU（自动补缺件 → 宽松隐式声明 → 空实现 → 链接）
        if: always()
        run: |
          set +e
          set -x
          cd xnu
          NCPU=$(sysctl -n hw.ncpu)
          MAKE="make -j$NCPU ARCH_CONFIGS=ARM64 KERNEL_CONFIGS=RELEASE"

          echo "########## PPL/SART 相关宏在哪些地方 ==="
          grep -rn "HAS_PPL\|CONFIG_PPL" osfmk/conf/*.arm64 osfmk/conf/MASTER* 2>/dev/null | head -20 || true
          grep -rn "ppl/sart.h\|ppl/uat.h" osfmk/arm/pmap/*.c osfmk/arm64/*.c 2>/dev/null | head -10 || true

          echo "########## pass 1 ##########"
          $MAKE > pass1.log 2>&1
          tail -15 pass1.log

          # 私有系统寄存器：从报错取行号后注释
          ASM=osfmk/arm64/machine_routines_asm.s
          grep -oE "machine_routines_asm\.s:[0-9]+" pass1.log 2>/dev/null | cut -d: -f2 | sort -un > /tmp/spr.txt
          while read -r ln; do
            if [ -n "$ln" ]; then
              sed -i "" "${ln}s|^|// fuxi: apple SPR not on snapdragon |" "$ASM"
            fi
          done < /tmp/spr.txt

          # 循环：缺头文件就补；调用未声明函数就写替身声明
          echo "########## 编译循环 ##########"
          i=0
          while [ "$i" -lt 10 ]; do
            i=$((i + 1))
            echo "--- 第 $i 轮 ---"
            $MAKE > pass3.log 2>&1

            MISS=$(grep -oE "fatal error: '[^']+' file not found" pass3.log | head -1 | sed "s/.*'\(.*\)'.*/\1/")
            if [ -n "$MISS" ]; then
              echo "缺头文件: $MISS"
              case "$MISS" in
                sys/*|net/*|vfs/*|dev/*) TARGET="bsd/$MISS" ;;
                libkern/*) TARGET="libkern/$MISS" ;;
                *) TARGET="osfmk/$MISS" ;;
              esac
              mkdir -p "$(dirname "$TARGET")"
              [ -f "$TARGET" ] || printf "/* fuxi: 替身头（%s） */\n" "$MISS" > "$TARGET"
              continue
            fi

            UNDECL=$(grep -oE "call to undeclared function '[a-zA-Z_0-9]+'" pass3.log | head -20 | sed "s/.*'\(.*\)'/\1/" | sort -u)
            if [ -n "$UNDECL" ]; then
              echo "未声明函数: $(echo $UNDECL)"
              # 写进一个全局替身声明头，并让 pmap.c 等文件包含它
              DECL=osfmk/arm64/fuxi_decls.h
              if [ ! -f "$DECL" ]; then
                printf "/* fuxi: 为 Apple 私有函数提供声明（实现在 fuxi_stubs.c） */\n#ifndef FUXI_DECLS_H\n#define FUXI_DECLS_H\n" > "$DECL"
              fi
              for fn in $UNDECL; do
                grep -q "\b$fn\b" "$DECL" || printf "extern void %s();\n" "$fn" >> "$DECL"
              done
              printf "#endif\n" >> "$DECL"
              # 注入到报错的文件里（在第一条 #include 之前）
              BADFILE=$(grep -oE "/[^ :]*\.c:[0-9]+:[0-9]+: error: call to undeclared" pass3.log | head -1 | cut -d: -f1)
              if [ -n "$BADFILE" ] && [ -f "$BADFILE" ]; then
                REL=$(echo "$BADFILE" | sed "s|$PWD/||")
                if ! grep -q "fuxi_decls.h" "$REL"; then
                  sed -i "" "1i\\
#include <arm64/fuxi_decls.h>
" "$REL"
                  echo "已把 fuxi_decls.h 注入 $REL"
                fi
              fi
              continue
            fi

            echo "没有缺件错误了"
            break
          done
          tail -25 pass3.log

          # 未定义符号 → 空实现
          python3 "$GITHUB_WORKSPACE/tools/gen_stubs.py" pass3.log osfmk/arm64/fuxi_stubs.c
          if ! grep -q "osfmk/arm64/fuxi_stubs.c" osfmk/conf/files.arm64; then
            printf "osfmk/arm64/fuxi_stubs.c\tstandard\n" >> osfmk/conf/files.arm64
          fi

          echo "########## 最终链接 ##########"
          $MAKE > pass4.log 2>&1
          tail -45 pass4.log

          echo "########## 产出物 ##########"
          ls -lh BUILD/obj/RELEASE_ARM64_VMAPPLE/kernel* 2>/dev/null || echo "还没有 kernel"

          cat pass1.log pass3.log pass4.log > build.log
          cp -f pass1.log pass3.log pass4.log build.log .. 2>/dev/null || true
'''
lines[s:e] = NEW_BUILD.split("\n")
io.open(W, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
print("已替换构建步骤")

# 自检
lines2 = io.open(W, encoding="utf-8").read().split("\n")
bad = [i for i, l in enumerate(lines2, 1)
       if not l.strip().startswith("#") and l.count('"') % 2]
print("引号不配对:", bad[:5] if bad else "无")
print("总行数:", len(lines2))
