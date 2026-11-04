#!/usr/bin/env python3
"""解析 fuxi 设备树里的 UFS 节点（控制器 / PHY / 相关时钟、中断）。"""

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


def cells(v):
    n = len(v) // 4
    return list(struct.unpack_from(">" + str(n) + "I", v, 0))


def regs(v):
    c = cells(v)
    out = []
    if len(c) % 4 == 0 and len(c) >= 4:
        for i in range(0, len(c), 4):
            out.append(((c[i] << 32) | c[i + 1], (c[i + 2] << 32) | c[i + 3]))
    elif len(c) % 2 == 0:
        for i in range(0, len(c), 2):
            out.append((c[i], c[i + 1]))
    return out


root = parse(open(DTB, "rb").read())


def walk(n, path=""):
    p = path + "/" + n.name if n.name else path
    yield p, n
    for c in n.children:
        yield from walk(c, p)


for path, node in walk(root):
    low = path.lower()
    if ("ufs" not in low and "ufshc" not in low) or "reserved" in low:
        continue
    comp = ""
    for k, v in node.props:
        if k == "compatible":
            comp = v.split(b"\x00")[0].decode("latin1")
    if "reserved" in comp:
        continue
    print("=" * 64)
    print(path)
    if comp:
        print("  compatible :", comp)
    for k, v in node.props:
        if k == "reg":
            print("  reg        :", ", ".join("0x%x len 0x%x" % r for r in regs(v)))
        elif k == "interrupts":
            print("  interrupts :", " ".join("0x%x" % x for x in cells(v)))
        elif k == "status":
            print("  status     :", v.split(b"\x00")[0].decode("latin1"))
        elif k in ("clock-names", "freq-table-hz", "vdd-hba-supply", "vcc-supply",
                   "vccq-supply", "vccq2-supply", "lanes-per-direction", "phy-names"):
            print("  %-14s: %s" % (k, "".join(chr(c) for c in v if 32 <= c < 127) or
                                   " ".join("0x%x" % x for x in cells(v))))
    print()
