#!/usr/bin/env python3
"""对比 Apple 内核与我们内核的导出符号集合。

Apple 的 kernelcache 内核符号表被剥离，但保留 LC_DYLD_INFO_ONLY 的导出树（export trie），
prelink 时正是靠它把"原内核某个地址"映射回符号名。所以只要我们的内核导出了这些名字，
指针重绑就能成立。
"""

import io
import struct
import sys
import zipfile

IPSW = r"E:\download\iPhone10,3,iPhone10,6_16.7.16_20H392_Restore.ipsw"
ENTRY = "kernelcache.release.iphone10b"
OURS = r"E:\download\xnu-kernel-21\out\kernel.development.fuxi"
KC_KERNEL_OFF = 0x1C

LC_DYLD_INFO = 0x22
LC_DYLD_INFO_ONLY = 0x80000022


def load_kc() -> bytes:
    import lzfse
    raw = zipfile.ZipFile(IPSW).read(ENTRY)
    i = 1
    ln = raw[i]; i += 1
    if ln & 0x80:
        n = ln & 0x7F
        total = int.from_bytes(raw[i:i + n], "big")
        i += n
    else:
        total = ln
    end = i + total
    items = []
    while i < end:
        tag = raw[i]; i += 1
        l2 = raw[i]; i += 1
        if l2 & 0x80:
            n = l2 & 0x7F
            l2 = int.from_bytes(raw[i:i + n], "big")
            i += n
        items.append((tag, raw[i:i + l2]))
        i += l2
    payload = next(v for tag, v in items if tag == 0x04)
    return lzfse.decompress(payload)


def load_commands(data, at):
    ncmds, sizeofcmds = struct.unpack_from("<II", data, at + 16)
    p = at + 32
    out = []
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", data, p)
        out.append((cmd, p, size))
        p += size
    return out


def segments(data, at):
    out = []
    for cmd, p, size in load_commands(data, at):
        if cmd == 0x19:
            name = data[p + 8:p + 24].split(b"\0")[0].decode("latin1")
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<4Q", data, p + 24)
            out.append(dict(name=name, va=vmaddr, size=vmsize, off=fileoff, fsize=filesize))
    return out


def uleb(buf, i):
    result = shift = 0
    while True:
        b = buf[i]; i += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, i
        shift += 7


def export_trie_names(data, at):
    """解析导出树，返回 {name: address}"""
    segs = segments(data, at)
    trie_off = None
    for cmd, p, size in load_commands(data, at):
        if cmd in (LC_DYLD_INFO_ONLY, LC_DYLD_INFO):
            export_off, export_size = struct.unpack_from("<II", data, p + 40)
            trie_off = export_off
            break
    if trie_off is None:
        return None
    # 导出树的 file offset 是相对"镜像第 0 个段的文件基址"
    base = min(s["off"] for s in segs if s["fsize"]) if segs else 0
    trie = data[base + trie_off:]

    out = {}
    stack = [(b"", 0)]
    seen = set()
    while stack:
        prefix, node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        i = node
        try:
            terminal_size, i = uleb(trie, i)
        except IndexError:
            continue
        if terminal_size:
            j = i
            flags, j = uleb(trie, j)
            if flags & 0x08:          # EXPORT_SYMBOL_FLAGS_REEXPORT
                pass
            else:
                addr, j = uleb(trie, j)
                out[prefix.decode("latin1")] = addr
            i += terminal_size
        try:
            nchild = trie[i]; i += 1
        except IndexError:
            continue
        for _ in range(nchild):
            end = trie.index(b"\0", i)
            edge = trie[i:end]
            i = end + 1
            off, i = uleb(trie, i)
            stack.append((prefix + edge, off if off else 0))
    return out


def symtab_names(data, at):
    for cmd, p, size in load_commands(data, at):
        if cmd != 0x2:
            continue
        symoff, nsyms, stroff, strsize = struct.unpack_from("<4I", data, p + 8)
        names = set()
        for i in range(nsyms):
            o = symoff + i * 16
            if o + 16 > len(data):
                break
            strx, ntype, sect, desc, value = struct.unpack_from("<IBBHQ", data, o)
            n_type = ntype & 0x0E
            # 只要已定义符号（N_SECT/N_ABS），不要求外部
            if n_type not in (0x0E, 0x02) or value == 0:
                continue
            end = data.find(b"\0", stroff + strx)
            names.add(data[stroff + strx:end].decode("latin1", "replace"))
        return names
    return None


def main() -> int:
    print("加载 Apple kernelcache ...")
    kc = load_kc()[KC_KERNEL_OFF:]   # 归一化：内核镜像从 0x1c 开始

    print("解析 Apple 内核符号表 ...")
    apple_syms = symtab_names(kc, 0)
    if not apple_syms:
        print("  没有符号表")
        return 1
    apple_exports = {n: 0 for n in apple_syms}
    print(f"  Apple 内核符号: {len(apple_exports):,}")

    print("解析我们内核的符号 ...")
    ours_data = io.open(OURS, "rb").read()
    our_syms = symtab_names(ours_data, 0)
    our_exports = export_trie_names(ours_data, 0) or {}
    print(f"  我们的符号表: {len(our_syms):,}，导出树: {len(our_exports):,}")

    have = set(our_syms or set()) | set(our_exports.keys())
    # Apple 导出名里去掉前导下划线再比（Mach-O 里都没下划线，保持一致）
    missing = sorted(n for n in apple_exports if n not in have)
    print(f"\n  Apple 导出 {len(apple_exports):,} 个，我们缺 {len(missing):,} 个"
          f"（覆盖率 {(1 - len(missing) / len(apple_exports)) * 100:.1f}%）")

    if missing:
        print("\n  缺失符号（前 40）:")
        for s in missing[:40]:
            print("    " + s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
