"""adt_fix_fuxi: 把 gic 节点的 virtual-timer-intid 改成 fuxi 真值 19。"""

import io

P = r"E:\ios-on-fuxi\tools\adt_fix_fuxi.py"
t = io.open(P, encoding="utf-8").read()

if "set_vtimer_intid" not in t:
    add = '''

VTIMER_INTID = 19   # fuxi 真机（DT: GIC_PPI 3）；QEMU/sweet 是 27


def set_vtimer_intid(node):
    """把 gic 节点的 virtual-timer-intid 改成 fuxi 的真值"""
    if node_name(node) == b"gic":
        found = False
        for i, (key, flags, val) in enumerate(node.props):
            if key == "virtual-timer-intid":
                node.props[i] = (key, flags, struct.pack("<I", VTIMER_INTID))
                found = True
        return found
    for c in node.children:
        if set_vtimer_intid(c):
            return True
    return False
'''
    anchor = "def main() -> int:"
    assert anchor in t
    t = t.replace(anchor, add.lstrip("\n") + "\n\n" + anchor, 1)

    t = t.replace("    fb_ok = set_fbcon_reg(root)",
                  "    fb_ok = set_fbcon_reg(root)\n    timer_ok = set_vtimer_intid(root)")
    t = t.replace('print(f"fbcon 帧缓冲: {fb_ok}")',
                  'print(f"fbcon 帧缓冲: {fb_ok}")\n    print(f"vtimer INTID={VTIMER_INTID}: {timer_ok}")')
    io.open(P, "w", encoding="utf-8", newline="\n").write(t)
    print("adt_fix_fuxi.py: 已加 virtual-timer-intid -> 19")
else:
    print("已有 set_vtimer_intid")
