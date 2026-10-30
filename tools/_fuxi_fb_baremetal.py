"""把内核侧的帧缓冲地址改成裸机阶段真正的 0xB8000000。

背景：
  · UEFI GOP 报的 FB 是 0xB0000000（UEFI 自己的那套显示）
  · 裸机（ABL）阶段真正的 splash 帧缓冲是 0xB8000000（设备树 splash_region）
  · 内核补丁 0010/0012 里的早期标记写死 0xB0000000 → 画面看不到
  · ADT 里 fuxi-fbcon 的 reg 也是 0xB0000000 → XNU 的 fbcon 控制台同样看不到

改动：
  1) xnu/patches/*.patch：0xB0000000 -> 0xB8000000
  2) tools/adt_fix_fuxi.py：强制 fuxi-fbcon reg = 0xB8000000
"""

import glob
import io

FB_OLD = "0xB0000000"
FB_NEW = "0xB8000000"

total = 0
for f in sorted(glob.glob(r"E:\ios-on-fuxi\xnu\patches\*.patch")):
    t = io.open(f, encoding="utf-8").read()
    n = t.count(FB_OLD)
    if n:
        t = t.replace(FB_OLD, FB_NEW)
        io.open(f, "w", encoding="utf-8", newline="\n").write(t)
        print(f"  {f.split(chr(92))[-1]}: {n} 处")
        total += n
print(f"补丁合计 {total} 处")

# ADT 生成器里强制 fuxi-fbcon
P = r"E:\ios-on-fuxi\tools\adt_fix_fuxi.py"
t = io.open(P, encoding="utf-8").read()

if "set_fbcon_reg" not in t:
    add = '''

FB_BASE, FB_SIZE = 0xB8000000, 0x9E4000   # 裸机阶段真正显示的 splash 帧缓冲


def set_fbcon_reg(node):
    """把 fuxi-fbcon 节点的 reg 强制成裸机可见的帧缓冲"""
    if node_name(node) == b"fuxi-fbcon":
        for i, (key, flags, val) in enumerate(node.props):
            if key == "reg":
                node.props[i] = (key, flags, struct.pack("<2Q", FB_BASE, FB_SIZE))
                return True
        return False
    for c in node.children:
        if set_fbcon_reg(c):
            return True
    return False
'''
    anchor = "def main() -> int:"
    assert anchor in t
    t = t.replace(anchor, add.lstrip("\n") + "\n\n" + anchor, 1)

    t = t.replace("    gic_ok = set_gic_absolute(root)",
                  "    gic_ok = set_gic_absolute(root)\n    fb_ok = set_fbcon_reg(root)")
    t = t.replace('print(f"gic 改成绝对地址: {gic_ok}")',
                  'print(f"gic 改成绝对地址: {gic_ok}")\n    print(f"fbcon 帧缓冲: {fb_ok}")')
    io.open(P, "w", encoding="utf-8", newline="\n").write(t)
    print("adt_fix_fuxi.py: 已强制 fuxi-fbcon reg = 0xB8000000")
else:
    print("adt_fix_fuxi.py: 已经有 set_fbcon_reg")
