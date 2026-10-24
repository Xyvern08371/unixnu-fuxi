import io
import sys

P = r"E:\ios-on-fuxi\.github\workflows\build-xnu.yml"
lines = io.open(P, encoding="utf-8").read().split("\n")

# 找到 "构建 XNU" 步骤的范围
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
    s = lines[end].strip()
    if s.startswith("- name:") or s.startswith("- uses:"):
        break
    end += 1

NEW = r'''      - name: 构建 XNU（手工汇编 start.o，含完整 include 路径）
        run: |
          exec > >(tee -a build.log) 2>&1
          set -x
          cd xnu
          NCPU=$(sysctl -n hw.ncpu)
          OBJ=BUILD/obj/RELEASE_ARM64_VMAPPLE

          echo "=== 关键头文件在哪 ==="
          find . -name board_config.h -not -path "./BUILD/*" 2>/dev/null | head -5
          find . -name tunables.s -not -path "./BUILD/*" 2>/dev/null | head -5
          find . -name assym.s 2>/dev/null | head -5

          echo "=== pass 1 ==="
          make -j"$NCPU" ARCH_CONFIGS=ARM64 KERNEL_CONFIGS=RELEASE || true

          echo "=== 手工汇编 start.o ==="
          INCS="-I. -I$OBJ/EXPORT_HDRS -I$OBJ/osfmk/RELEASE -I$OBJ"
          for d in osfmk bsd pexpert libkern iokit security san osfmk/arm64; do
            if [ -d "$d" ]; then INCS="$INCS -I$d"; fi
          done
          echo "INCS=$INCS"
          mkdir -p "$OBJ/osfmk/arm64"
          clang -c -o "$OBJ/osfmk/arm64/start.o" osfmk/arm64/start.s $INCS \
            -DARM64=1 -DKERNEL=1 -DPRIVATE=1 -DXNU_TARGET_OS_OSX=1 2>&1 | head -30 || true
          ls -l "$OBJ/osfmk/arm64/start.o" 2>/dev/null || echo "start.o 仍未生成"
          nm "$OBJ/osfmk/arm64/start.o" 2>/dev/null | grep -i __start | head -3 || true

          echo "=== pass 2 ==="
          make -j"$NCPU" ARCH_CONFIGS=ARM64 KERNEL_CONFIGS=RELEASE || true

          echo "=== 产出物 ==="
          ls -lh "$OBJ"/kernel* 2>/dev/null || echo "还没有 kernel"
          find BUILD -name "kernel.release*" -type f | head -5
'''

lines[start:end] = NEW.split("\n")
io.open(P, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
print(f"已替换构建步骤：原行 {start+1}..{end}")

# 自检
lines2 = io.open(P, encoding="utf-8").read().split("\n")
bad = [i for i, l in enumerate(lines2, 1)
       if not l.strip().startswith("#") and l.count('"') % 2]
print("引号不配对行:", bad[:5] if bad else "无")
d = 0
for l in lines2:
    s = l.strip()
    if s.startswith("for ") and s.endswith("; do"):
        d += 1
    elif s == "done":
        d -= 1
print("循环 depth:", d, "(应为 0)")
