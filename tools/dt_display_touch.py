#!/usr/bin/env python3
"""从 fuxi 设备树里挖出显示 / 触控相关的硬件信息。

输出：节点路径、compatible、reg、interrupts、以及面板/触控的关键属性。
"""

import re
import struct
import sys

DTB = sys.argv[1] if len(sys.argv) > 1 else r"E:\ios-on-fuxi\rom\device\fuxi_runtime.dtb"


class Node:
    def __init__(self, name):
        self.name = name
        self.props = []
        self.children = []


def parse(buf):
    offs, offstr = struct.unpack_from(">II", buf, 8)
    pos = offs
    stack = [Node("")]
    while True:
        tok, = struct.unpack_from(">I", buf, pos)
        pos += 4
        if tok == 1:
            end = buf.index(b"\0", pos)
            name = buf[pos:end].decode("latin1")
            pos = (end + 4) & ~3
            n = Node(name)
            stack[-1].children.append(n)
            stack.append(n)
        elif tok == 2:
            stack.pop()
        elif tok == 3:
            ln, nm = struct.unpack_from(">II", buf, pos)
            pos += 8
            val = buf[pos:pos + ln]
            pos = (pos + ln + 3) & ~3
            end = buf.index(b"\0", offstr + nm)
            key = buf[offstr + nm:end].decode("latin1")
            stack[-1].props.append((key, val))
        elif tok == 9:
            break
    return stack[0]


def getstr(node, key):
    for k, v in node.props:
        if k == key:
            return v.split(b"\0")[0].decode("latin1")
    return None


def getvals(node, key, fmt="<I"):
    for k, v in node.props:
        if k == key:
            n = len(v) // struct.calcsize(fmt)
            return list(struct.unpack_from("<" + str(n) + fmt[1], v, 0))
    return None


def path_of(node, path=""):
    p = path + "/" + node.name if node.name else path
    yield p, node
    for c in node.children:
        yield from path_of(c, p)


root = parse(open(DTB, "rb").read())

PAT = re.compile(r"touch|panel|dsi|mdss|dpu|disp|goodix|novatek|focaltech|synaptics|backlight|wled", re.I)

print(f"=== {DTB} 里显示/触控相关节点 ===\n")
for path, node in path_of(root):
    comp = getstr(node, "compatible") or ""
    if not (PAT.search(path) or PAT.search(comp)):
        continue
    if "reserved-memory" in path or "/soc" == path:
        continue

    reg = getvals(node, "reg", "<Q")
    irq = getvals(node, "interrupts", "<I")
    status = getstr(node, "status")
    line = f"{path}"
    print(line)
    if comp:
        print(f"    compatible : {comp}")
    if reg:
        print(f"    reg        : " + " ".join("0x%x" % v for v in reg[:8]))
    if irq:
        print(f"    interrupts : " + " ".join(str(v) for v in irq[:8]))
    if status:
        print(f"    status     : {status}")
    keys = [k for k, _ in node.props]
    interesting = [k for k in keys if re.search(r"panel|reset|vdd|vcc|iovcc|pinctrl|spi|clock|supply|label|compatible", k, re.I)]
    if interesting:
        shown = ", ".join(interesting[:12])
        print(f"    关键属性   : {shown}")
    print()
