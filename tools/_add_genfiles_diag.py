import io
import sys

P = r"E:\ios-on-fuxi\.github\workflows\build-xnu.yml"
lines = io.open(P, encoding="utf-8").read().split("\n")

# 在 "打包产物" 之前插入一个诊断步骤
anchor = None
for i, l in enumerate(lines):
    if l.strip().startswith("- name:") and "打包产物" in l:
        anchor = i
        break
if anchor is None:
    print("找不到打包步骤")
    sys.exit(1)

NEW = r'''      - name: 排查 tunables.s / assym.s 的生成方式
        if: always()
        run: |
          exec > >(tee -a genfiles.log) 2>&1
          cd xnu
          OBJ=BUILD/obj/RELEASE_ARM64_VMAPPLE

          echo "=== 1. tunables 目录内容 ==="
          ls -la osfmk/arm64/tunables/ 2>/dev/null || echo "(没有该目录)"

          echo "=== 2. 谁提到 tunables.s ==="
          grep -rn "tunables\.s" makedefs osfmk/conf SETUP 2>/dev/null | head -20 || true

          echo "=== 3. 谁提到 tunables（脚本/规则）==="
          grep -rln "tunables" SETUP makedefs 2>/dev/null | head -10 || true

          echo "=== 4. 构建目录里已生成的东西 ==="
          ls -la "$OBJ/osfmk/RELEASE/" 2>/dev/null | head -30 || echo "(无)"
          echo "--- 找 assym.s / tunables.s ---"
          find BUILD -name "assym.s" 2>/dev/null | head -5
          find BUILD -name "tunables*.s" 2>/dev/null | head -5

          echo "=== 5. 树里所有 tunables 相关文件 ==="
          find . -name "*tunables*" -not -path "./BUILD/*" 2>/dev/null | head -20

          echo "=== 6. Makefile 里 start.o 的依赖与命令 ==="
          grep -n -B2 -A8 "start.s" "$OBJ/osfmk/RELEASE/Makefile" 2>/dev/null | head -40 || true

'''

lines[anchor:anchor] = NEW.split("\n")
io.open(P, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
print(f"已在行 {anchor+1} 前插入诊断步骤")

# 把 genfiles.log 加进产物
text = io.open(P, encoding="utf-8").read()
if "genfiles.log" in text and "            genfiles.log" not in text:
    text = text.replace("            startup.log", "            startup.log\n            genfiles.log")
    io.open(P, "w", encoding="utf-8", newline="\n").write(text)
    print("已把 genfiles.log 加入产物")

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
