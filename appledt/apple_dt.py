#!/usr/bin/env python3
"""apple_dt.py -- FDT(DTB) 读写器 + Apple 风格设备树合成器

纯标准库, 无第三方依赖。

子命令:
  synth   <profile.json> -o out.dtb    从 profile 合成设备树
  dump    <file.dtb>                   解析并以类 dtc 文本打印
  from-fdt <in.dtb> -o out.dtb         读入再吐出(验证解析器/结构对比)

设计原则:
  * 代码是"通用 FDT 引擎" + "profile 驱动的 Apple DT 合成"两层。
  * Apple 设备树的具体属性名/取值属于"待核实数据", 一律放在 profile 里,
    不写死在代码中。这样换成 iPhone 其他型号或修正字段时不用改代码。
  * 本工具不解析、不解密、不生成任何苹果私有二进制(内核/文件系统)。
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from collections import OrderedDict

# ---------------------------------------------------------------- FDT 常量

MAGIC = 0xD00DFEED
VERSION = 17
LAST_COMP_VERSION = 16
HEADER_LEN = 40

FDT_BEGIN_NODE = 0x1
FDT_END_NODE = 0x2
FDT_PROP = 0x3
FDT_NOP = 0x4
FDT_END = 0x9


class DtError(ValueError):
    pass


def _align4(x: int) -> int:
    return (x + 3) & ~3


# ---------------------------------------------------------------- 树模型

class Node:
    """一个设备树节点。props 保持插入顺序(序列化后字节可复现)。"""

    __slots__ = ("name", "props", "children")

    def __init__(self, name: str = "") -> None:
        self.name = name
        self.props: "OrderedDict[str, bytes]" = OrderedDict()
        self.children: list[Node] = []

    # -- 构造
    def add(self, name: str) -> "Node":
        child = Node(name)
        self.children.append(child)
        return child

    def set(self, name: str, value: bytes) -> "Node":
        self.props[name] = bytes(value)
        return self

    # -- 查询
    def find(self, path: str) -> "Node":
        """'/chosen' -> 节点; 路径以 '/' 开头, 根用 '/'。"""
        if not path.startswith("/"):
            raise DtError("路径必须以 / 开头: %r" % path)
        cur = self
        for part in [p for p in path.split("/") if p]:
            for c in cur.children:
                if c.name == part:
                    cur = c
                    break
            else:
                raise DtError("路径不存在: %r (缺 %r)" % (path, part))
        return cur

    def try_find(self, path: str) -> "Node | None":
        try:
            return self.find(path)
        except DtError:
            return None

    def get_str(self, prop: str, default: str | None = None) -> str | None:
        raw = self.props.get(prop)
        if raw is None:
            return default
        return raw.split(b"\0", 1)[0].decode("utf-8", "replace")

    def get_u32(self, prop: str, default: int | None = None) -> int | None:
        raw = self.props.get(prop)
        if raw is None:
            return default
        if len(raw) != 4:
            raise DtError("属性 %r 不是单个 u32 (len=%d)" % (prop, len(raw)))
        return struct.unpack(">I", raw)[0]

    def walk(self, depth: int = 0):
        yield self, depth
        for c in self.children:
            yield from c.walk(depth + 1)

    def __eq__(self, other) -> bool:
        if not isinstance(other, Node):
            return NotImplemented
        if self.name != other.name:
            return False
        if list(self.props.items()) != list(other.props.items()):
            return False
        return self.children == other.children

    def __repr__(self) -> str:
        return "<Node %r props=%d children=%d>" % (
            self.name, len(self.props), len(self.children))


# ---------------------------------------------------------------- 序列化

class _Writer:
    def __init__(self) -> None:
        self.strings = bytearray()
        self._offsets: dict[str, int] = {}

    def str_off(self, name: str) -> int:
        if name in self._offsets:
            return self._offsets[name]
        off = len(self.strings)
        self._offsets[name] = off
        self.strings += name.encode("utf-8") + b"\0"
        return off

    def emit(self, node: Node, out: bytearray) -> None:
        out += struct.pack(">I", FDT_BEGIN_NODE)
        nb = node.name.encode("utf-8")
        out += nb + b"\0"
        pad = _align4(len(nb) + 1) - (len(nb) + 1)
        out += b"\0" * pad

        for key, val in node.props.items():
            out += struct.pack(">III", FDT_PROP, len(val), self.str_off(key))
            out += val
            out += b"\0" * (_align4(len(val)) - len(val))

        for child in node.children:
            self.emit(child, out)
        out += struct.pack(">I", FDT_END_NODE)


def serialize(root: Node, boot_cpuid: int = 0) -> bytes:
    """把树序列化成合法的 DTB blob。"""
    w = _Writer()
    struct_blob = bytearray()
    w.emit(root, struct_blob)
    struct_blob += struct.pack(">I", FDT_END)

    off_rsv = HEADER_LEN                      # 40, 8 字节对齐
    off_struct = off_rsv + 16                 # 16 字节的保留区终止符
    off_strings = off_struct + len(struct_blob)
    total = off_strings + len(w.strings)

    header = struct.pack(
        ">10I",
        MAGIC, total, off_struct, off_strings, off_rsv,
        VERSION, LAST_COMP_VERSION, boot_cpuid,
        len(w.strings), len(struct_blob),
    )
    assert len(header) == HEADER_LEN
    return bytes(header) + (b"\0" * 16) + bytes(struct_blob) + bytes(w.strings)


# ---------------------------------------------------------------- 解析

def parse(blob: bytes) -> Node:
    if len(blob) < HEADER_LEN:
        raise DtError("blob 太短: %d" % len(blob))
    (magic, total, off_struct, off_strings, _off_rsv,
     ver, _lastver, _cpuid, size_str, size_struct) = struct.unpack(">10I", blob[:40])

    if magic != MAGIC:
        raise DtError("magic 不对: 0x%08X" % magic)
    if ver < 16 or ver > VERSION:
        raise DtError("不支持的结构版本: %d" % ver)
    if total > len(blob):
        raise DtError("header 声称 %d 字节, 实际只有 %d" % (total, len(blob)))
    if off_struct + size_struct > len(blob):
        raise DtError("struct 区越界")
    if off_strings + size_str > len(blob):
        raise DtError("strings 区越界")

    strings = blob[off_strings:off_strings + size_str]
    pos, end = off_struct, off_struct + size_struct
    stack: list[Node] = []
    root: Node | None = None
    saw_end = False

    def cstr(buf: bytes, off: int) -> str:
        if off >= len(buf):
            raise DtError("字符串偏移越界: %d" % off)
        nul = buf.find(b"\0", off)
        if nul < 0:
            raise DtError("字符串未以 NUL 结尾: %d" % off)
        return buf[off:nul].decode("utf-8", "replace")

    while pos < end:
        if pos + 4 > end:
            raise DtError("token 截断")
        token = struct.unpack(">I", blob[pos:pos + 4])[0]
        pos += 4

        if token == FDT_BEGIN_NODE:
            nul = blob.find(b"\0", pos, end)
            if nul < 0:
                raise DtError("节点名未以 NUL 结尾")
            node = Node(blob[pos:nul].decode("utf-8", "replace"))
            pos = _align4(nul + 1)
            if stack:
                stack[-1].children.append(node)
            elif root is None:
                root = node
            else:
                raise DtError("出现第二个根节点")
            stack.append(node)

        elif token == FDT_END_NODE:
            if not stack:
                raise DtError("END_NODE 没有对应的 BEGIN_NODE")
            stack.pop()

        elif token == FDT_PROP:
            if not stack:
                raise DtError("PROP 出现在节点之外")
            if pos + 8 > end:
                raise DtError("prop 头部截断")
            length, name_off = struct.unpack(">II", blob[pos:pos + 8])
            pos += 8
            if pos + length > end:
                raise DtError("prop 数据截断")
            name = cstr(strings, name_off)
            stack[-1].props[name] = bytes(blob[pos:pos + length])
            pos = _align4(pos + length)

        elif token == FDT_NOP:
            continue

        elif token == FDT_END:
            saw_end = True
            break

        else:
            raise DtError("未知 token 0x%X @ 0x%X" % (token, pos - 4))

    if root is None:
        raise DtError("没有根节点")
    if stack:
        raise DtError("有 %d 个节点没有闭合" % len(stack))
    if not saw_end:
        raise DtError("缺少 END token")
    return root


# ---------------------------------------------------------------- 取值编码

def _int(v) -> int:
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        return int(v, 0)
    raise DtError("不是整数: %r" % (v,))


def encode_value(desc: dict) -> bytes:
    """把 profile 里的取值描述编码成 DT 属性的原始字节。

    支持: str / strs / u32 / u32s / u64 / u64s / bytes(列表) / hex / bool / empty
    """
    if "str" in desc:
        return str(desc["str"]).encode("utf-8") + b"\0"
    if "strs" in desc:
        return b"".join(str(s).encode("utf-8") + b"\0" for s in desc["strs"])
    if "u32" in desc:
        return struct.pack(">I", _int(desc["u32"]))
    if "u32s" in desc:
        return b"".join(struct.pack(">I", _int(x)) for x in desc["u32s"])
    if "u64" in desc:
        return struct.pack(">Q", _int(desc["u64"]))
    if "u64s" in desc:
        return b"".join(struct.pack(">Q", _int(x)) for x in desc["u64s"])
    if "bytes" in desc:
        return bytes(bytearray(_int(x) & 0xFF for x in desc["bytes"]))
    if "hex" in desc:
        return bytes.fromhex(desc["hex"].replace(" ", "").replace(":", ""))
    if "bool" in desc:
        return b""          # DT 里布尔属性的惯例: 存在且长度为 0
    if "empty" in desc:
        return b""
    raise DtError("无法识别的取值描述: %r" % (desc,))


# ---------------------------------------------------------------- profile 合成

def build(profile: dict) -> Node:
    """profile -> Node。以 '_' 开头的键视为注释, 一律忽略。"""

    def make(spec: dict) -> Node:
        node = Node(str(spec.get("name", "")))
        for key, desc in (spec.get("props") or {}).items():
            if key.startswith("_"):
                continue
            node.set(key, encode_value(desc))
        for child in spec.get("children") or []:
            node.children.append(make(child))
        return node

    root = make(profile)
    if root.name != "":
        raise DtError("根节点名必须是空字符串, 现在是 %r" % root.name)
    return root


def load_profile(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------- 文本输出

def _fmt_value(raw: bytes) -> str:
    if len(raw) == 0:
        return "true"
    # 先试字符串: 以 NUL 结尾且内容全是可见字符
    if raw.endswith(b"\0") and len(raw) > 1:
        text = raw[:-1]
        if all(32 <= b < 127 for b in text):
            return '"%s"' % text.decode("ascii")
    if len(raw) == 4:
        return "<0x%08x>" % struct.unpack(">I", raw)[0]
    if len(raw) == 8:
        return "<0x%016x>" % struct.unpack(">Q", raw)[0]
    if len(raw) % 4 == 0 and len(raw) <= 32:
        cells = struct.unpack(">%dI" % (len(raw) // 4), raw)
        return "<" + " ".join("0x%x" % c for c in cells) + ">"
    return "[" + " ".join("%02x" % b for b in raw[:16]) + (
        " ..." if len(raw) > 16 else "") + "]"


def dump(root: Node, out=None) -> None:
    out = out or sys.stdout

    def rec(node: Node, depth: int, is_root: bool) -> None:
        pad = "    " * depth
        label = "/" if is_root else node.name
        out.write("%s%s {\n" % (pad, label))
        for key, val in node.props.items():
            out.write("%s    %-24s %s\n" % (pad, key, _fmt_value(val)))
        for child in node.children:
            rec(child, depth + 1, False)
        out.write("%s};\n" % pad)

    rec(root, 0, True)


# ---------------------------------------------------------------- CLI

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="apple_dt", description="FDT 读写 + Apple DT 合成")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_synth = sub.add_parser("synth", help="从 profile 合成 dtb")
    p_synth.add_argument("profile")
    p_synth.add_argument("-o", "--out", required=True)
    p_synth.add_argument("--cpuid", type=int, default=0)

    p_dump = sub.add_parser("dump", help="打印 dtb 内容")
    p_dump.add_argument("dtb")

    p_conv = sub.add_parser("from-fdt", help="读入 dtb 再吐出")
    p_conv.add_argument("dtb")
    p_conv.add_argument("-o", "--out", required=True)

    args = ap.parse_args(argv)

    try:
        if args.cmd == "synth":
            root = build(load_profile(args.profile))
            blob = serialize(root, boot_cpuid=args.cpuid)
            with open(args.out, "wb") as fh:
                fh.write(blob)
            print("写出 %s (%d 字节, %d 个节点)" % (
                args.out, len(blob), sum(1 for _ in root.walk())))
            return 0

        if args.cmd == "dump":
            with open(args.dtb, "rb") as fh:
                root = parse(fh.read())
            dump(root)
            return 0

        if args.cmd == "from-fdt":
            with open(args.dtb, "rb") as fh:
                root = parse(fh.read())
            blob = serialize(root)
            with open(args.out, "wb") as fh:
                fh.write(blob)
            print("往返成功: %s -> %s (%d 字节)" % (args.dtb, args.out, len(blob)))
            return 0

    except (DtError, OSError, json.JSONDecodeError) as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 1

    ap.error("未知命令")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
