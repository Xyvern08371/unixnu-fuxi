"""CI：优先用 rom/xnu/fuxi.adt（来自 kalama.adt 的改名版），没有才现场生成。"""

import io

W = r"E:\ios-on-fuxi\.github\workflows\build-fuxi-uefi.yml"
t = io.open(W, encoding="utf-8").read()

old = """          echo "=== 生成 Apple 设备树 ==="
          python3 tools/mkadt_fuxi.py rom/xnu/fuxi.adt || echo "mkadt 失败"
          ls -l rom/xnu/fuxi.adt"""

new = """          echo "=== 准备 Apple 设备树 ==="
          if [ -f rom/xnu/kalama.adt ]; then
            echo "用 kalama.adt 生成 fuxi 版（改节点名 + dram 锚点）"
            python3 tools/adt_fix_fuxi.py rom/xnu/kalama.adt rom/xnu/fuxi.adt || echo "adt_fix 失败"
          elif [ -f rom/xnu/fuxi.adt ]; then
            echo "用仓库里的 fuxi.adt"
          else
            echo "没有 ADT 源，现场生成"
            python3 tools/mkadt_fuxi.py rom/xnu/fuxi.adt || echo "mkadt 失败"
          fi
          ls -l rom/xnu/fuxi.adt"""

assert old in t, "ADT 步骤没找到"
t = t.replace(old, new, 1)

# 触发路径补上 adt 工具
if '"tools/**"' in t:
    pass  # 已含

io.open(W, "w", encoding="utf-8", newline="\n").write(t)
print("CI: ADT 步骤已更新")

lines = t.split("\n")
bad = [i for i, l in enumerate(lines, 1) if not l.strip().startswith("#") and l.count('"') % 2]
print("引号不配对:", bad[:5] if bad else "无")
