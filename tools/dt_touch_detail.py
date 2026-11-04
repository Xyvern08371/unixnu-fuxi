#!/usr/bin/env python3
"""解析 fuxi 触控链路（GENI SE -> I2C -> Goodix GT9916）的硬件参数。"""

import struct

DTB = r"E:\ios-on-fuxi\rom\device\fuxi_runtime.dtb"


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
            n = Node(buf[pos:end].decode("latin1"))
            pos = (end + 4) & ~3
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
            stack[-1].props.append((buf[offstr + nm:end].decode("latin1"), val))
        elif tok == 9:
            break
    return stack[0]


def cells(val):
    n = len(val) // 4
    return list(struct.unpack_from(">" + str(n) + "I", val, 0))


def regvals(v):
    c = cells(v)
    out = []
    if len(c) % 4 == 0 and len(c) >= 4:
        for i in range(0, len(c), 4):
            out.append(((c[i] << 32) | c[i + 1], (c[i + 2] << 32) | c[i + 3]))
    elif len(c) % 2 == 0:
        for i in range(0, len(c), 2):
            out.append((c[i], c[i + 1]))
    else:
        out.append((c[0] if c else 0, 0))
    return out


root = parse(open(DTB, "rb").read())


def walk(n, path=""):
    p = path + "/" + n.name if n.name else path
    yield p, n
    for c in n.children:
        yield from walk(c, p)


want = ("goodix", "i2c@a90000", "qupv3_1_geni_se@ac0000")
for path, node in walk(root):
    if not any(w in path for w in want):
        continue
    if path.count("/") > 4:
        continue
    print("=" * 66)
    print(path)
    for k, v in node.props:
        if k == "reg":
            print("  reg        :", ", ".join("0x%x len 0x%x" % r for r in regvals(v)))
        elif k == "interrupts":
            print("  interrupts :", " ".join("0x%x" % x for x in cells(v)))
        elif k in ("compatible", "status"):
            print("  %-11s: %s" % (k, v.split(b"\x00")[0].decode("latin1")))
        elif k in ("goodix,irq-gpio", "goodix,reset-gpio", "goodix,vdd-gpio",
                   "vdd_ana-supply", "vdd_dig-supply", "pinctrl-0", "pinctrl-1",
                   "pinctrl-names", "clock-frequency", "interrupt-names"):
            print("  %-11s: %s" % (k, " ".join("0x%x" % x for x in cells(v))))
    print()
