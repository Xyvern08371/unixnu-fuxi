#!/usr/bin/env python3
"""overlay.py -- FDT overlay 合并器 (等价于 libfdt 的 fdt_overlay_apply)

fuxi 的真实设备树 = vendor_boot 里的 kalama 基础树 + dtbo 里的 fuxi overlay。
不做合并, 拿到的树会缺一大半节点(面板/触控/PMIC 全是 overlay 加的)。

合并要做四件事, 顺序不能乱:
  1. 重编号: overlay 自带 phandle 从 1 开始, 和 base 撞车(实测 529 个全撞)。
     给 overlay 的每个 phandle 分配 base_max + i。
  2. 本地引用重定位: 按 __local_fixups__ 里记录的字节偏移, 把 overlay 内部
     指向自己节点的 phandle 换成新号。
  3. 外部引用解析: 按 __fixups__ 把 0xffffffff 占位符换成 base 里对应节点的
     phandle(靠 base 的 __symbols__ 把标签解析成路径)。
  4. 合并 fragment: 按 target / target-path 找到目标节点, 把 __overlay__
     子树递归并进去。

用法:
  python overlay.py base.dtb overlay.dtb -o merged.dtb
"""
from __future__ import annotations

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "appledt"))

import apple_dt as A


def u32(b: bytes) -> int:
    return struct.unpack(">I", b)[0]


def node_phandle(node: A.Node):
    p = node.props.get("phandle") or node.props.get("linux,phandle")
    return u32(p) if p and len(p) == 4 else None


def clone(node: A.Node) -> A.Node:
    out = A.Node(node.name)
    for k, v in node.props.items():
        out.props[k] = bytes(v)
    out.children = [clone(c) for c in node.children]
    return out


def walk_path(node: A.Node, prefix: str = ""):
    """遍历并给出每个节点在树里的绝对路径(根为空串)。"""
    yield node, prefix
    for c in node.children:
        yield from walk_path(c, prefix + "/" + c.name)


def find_by_phandle(root: A.Node, ph: int):
    for node, _ in root.walk():
        if node_phandle(node) == ph:
            return node
    return None


# ---------------------------------------------------------------- 合并

class MergeResult:
    def __init__(self) -> None:
        self.renumbered = 0
        self.local_patched = 0
        self.fixups_applied = 0
        self.fragments_applied = 0
        self.fragments_skipped: list[str] = []
        self.warnings: list[str] = []


def apply_overlay(base: A.Node, ov: A.Node) -> tuple[A.Node, MergeResult]:
    res = MergeResult()
    out = clone(base)

    # --- 1. 重编号 overlay 的 phandle
    base_phandles = [ph for ph in (node_phandle(n) for n, _ in out.walk()) if ph]
    next_ph = (max(base_phandles) if base_phandles else 0) + 1
    remap: dict[int, int] = {}
    for node, _ in ov.walk():
        ph = node_phandle(node)
        if ph is not None and ph not in remap:
            remap[ph] = next_ph
            next_ph += 1
    res.renumbered = len(remap)

    # --- 2. 按 __local_fixups__ 重定位 overlay 内部引用
    lf = ov.try_find("/__local_fixups__")
    if lf is not None:
        for node, path in walk_path(lf):
            if node is lf or not node.props:
                continue
            target = ov.try_find(path) if path else None
            if target is None:
                res.warnings.append("local_fixups 路径对不上: %s" % path)
                continue
            for prop, raw in node.props.items():
                data = bytearray(target.props.get(prop, b""))
                if len(raw) % 4:
                    res.warnings.append("local_fixups 偏移长度异常: %s:%s" % (path, prop))
                    continue
                for i in range(len(raw) // 4):
                    off = u32(raw[i * 4:i * 4 + 4])
                    if off + 4 > len(data):
                        res.warnings.append("local_fixups 偏移越界: %s:%s@%d" % (path, prop, off))
                        continue
                    old = u32(data[off:off + 4])
                    if old in remap:
                        struct.pack_into(">I", data, off, remap[old])
                        res.local_patched += 1
                target.props[prop] = bytes(data)

    # 节点自身的 phandle 属性也要换
    for node, _ in ov.walk():
        for key in ("phandle", "linux,phandle"):
            if key in node.props:
                old = u32(node.props[key])
                if old in remap:
                    node.props[key] = struct.pack(">I", remap[old])

    # --- 3. 解析 __fixups__ (0xffffffff -> base 节点的 phandle)
    fx = ov.try_find("/__fixups__")
    sym = out.try_find("/__symbols__")
    if fx is not None:
        for label, val in fx.props.items():
            base_path = None
            if sym is not None and label in sym.props:
                base_path = sym.props[label].split(b"\0")[0].decode("utf-8", "replace")
            if not base_path:
                res.warnings.append("找不到符号 %r 在 base 里的路径" % label)
                continue
            target = out.try_find(base_path)
            if target is None:
                res.warnings.append("符号 %r 指向的 base 节点不存在: %s" % (label, base_path))
                continue
            ph = node_phandle(target)
            if ph is None:
                res.warnings.append("base 节点没有 phandle: %s" % base_path)
                continue
            for entry in val.split(b"\0"):
                if not entry:
                    continue
                try:
                    path, prop, off_s = entry.decode().rsplit(":", 2)
                    off = int(off_s)
                except ValueError:
                    res.warnings.append("fixup 条目无法解析: %r" % entry[:60])
                    continue
                node = ov.try_find(path)
                if node is None or prop not in node.props:
                    res.warnings.append("fixup 目标不存在: %s:%s" % (path, prop))
                    continue
                data = bytearray(node.props[prop])
                if off + 4 <= len(data):
                    struct.pack_into(">I", data, off, ph)
                    node.props[prop] = bytes(data)
                    res.fixups_applied += 1

    # --- 4. 合并 fragment
    for frag in ov.children:
        if frag.name.startswith("__") or ("target" not in frag.props
                                          and "target-path" not in frag.props):
            continue
        target = None
        if "target-path" in frag.props:
            tpath = frag.props["target-path"].split(b"\0")[0].decode("utf-8", "replace")
            target = out.try_find(tpath)
            where = tpath
        else:
            ph = u32(frag.props["target"])
            if ph == 0xFFFFFFFF:
                res.fragments_skipped.append("%s (target 未解析)" % frag.name)
                continue
            target = find_by_phandle(out, ph)
            where = "phandle 0x%x" % ph

        if target is None:
            res.fragments_skipped.append("%s (目标 %s 不在 base 里)" % (frag.name, where))
            continue

        body = next((c for c in frag.children if c.name == "__overlay__"), None)
        if body is None:
            res.fragments_skipped.append("%s (没有 __overlay__)" % frag.name)
            continue

        _merge(target, body)
        res.fragments_applied += 1

    # --- 清理: fixups/symbols 在成品树里没有意义
    out.children = [c for c in out.children
                    if c.name not in ("__fixups__", "__local_fixups__", "__symbols__")]
    return out, res


def _merge(dst: A.Node, src: A.Node) -> None:
    for k, v in src.props.items():
        dst.props[k] = bytes(v)
    for sc in src.children:
        for dc in dst.children:
            if dc.name == sc.name:
                _merge(dc, sc)
                break
        else:
            dst.children.append(clone(sc))


# ---------------------------------------------------------------- 校验

def check(tree: A.Node) -> list[str]:
    """基本健全性检查: phandle 重复、节点数为 0。"""
    problems = []
    seen: dict[int, str] = {}
    for node, path in walk_path(tree):
        ph = node_phandle(node)
        if ph is None:
            continue
        if ph in seen:
            problems.append("phandle 0x%x 重复: %s 与 %s" % (ph, seen[ph], path))
        else:
            seen[ph] = path
    if not tree.children:
        problems.append("合并结果是空树")
    return problems


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="overlay", description="FDT overlay 合并")
    ap.add_argument("base")
    ap.add_argument("overlay", nargs="+")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("-q", "--quiet", action="store_true")
    args = ap.parse_args(argv)

    try:
        with open(args.base, "rb") as fh:
            tree = A.parse(fh.read())

        for path in args.overlay:
            with open(path, "rb") as fh:
                ov = A.parse(fh.read())
            tree, res = apply_overlay(tree, ov)
            if not args.quiet:
                print("合并 %s" % path)
                print("  重编号 phandle %d 个, 本地引用 %d 处, 外部符号 %d 处"
                      % (res.renumbered, res.local_patched, res.fixups_applied))
                print("  fragment 应用 %d 个, 跳过 %d 个"
                      % (res.fragments_applied, len(res.fragments_skipped)))
                for s in res.fragments_skipped[:8]:
                    print("    跳过: %s" % s)
                for w in res.warnings[:8]:
                    print("    警告: %s" % w)
                if len(res.warnings) > 8:
                    print("    ... 另有 %d 条警告" % (len(res.warnings) - 8))

        blob = A.serialize(tree)
        with open(args.out, "wb") as fh:
            fh.write(blob)

        n = sum(1 for _ in walk_path(tree))
        problems = check(tree)
        if not args.quiet:
            print("写出 %s (%d 节点, %d 字节)" % (args.out, n, len(blob)))
            print("校验: %s" % ("通过" if not problems else "%d 个问题" % len(problems)))
            for p in problems[:5]:
                print("  %s" % p)
        return 0 if not problems else 2

    except (A.DtError, OSError) as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
