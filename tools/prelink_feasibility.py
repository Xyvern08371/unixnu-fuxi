#!/usr/bin/env python3
"""prelink 可行性报告。

对比两个内核的符号表：
  · Apple kernelcache 里的内核（xnu-8796.142.1）
  · 我们自己编译的内核（xnu-8796.101.5）
看 Apple 有、我们没有的符号，并检查 APFS kext 是否依赖这些符号。

只读分析，不导出 Apple 二进制。
"""

import io
import re
import struct
import sys
import zipfile

IPSW = r"E:\download\iPhone10,3,iPhone10,6_16.7.16_20H392_Restore.ipsw"
ENTRY = "kernelcache.release.iphone10b"
OURS = r"E:\download\xnu-kernel-21\out\kernel.development.fuxi"
KC_HEADER_OFF = 0x1C


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


def macho_header(data, at):
    magic, cpu, sub, kind, ncmds, sizeofcmds = struct.unpack_from("<6I", data, at)
    return dict(magic=magic, cpu=cpu, kind=kind, ncmds=ncmds, sizeofcmds=sizeofcmds)


def segments(data, at):
    ncmds, = struct.unpack_from("<I", data, at + 16)
    p = at + 32
    out = []
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", data, p)
        if cmd == 0x19:
            name = data[p + 8:p + 24].split(b"\0")[0].decode("latin1")
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<4Q", data, p + 24)
            out.append(dict(name=name, va=vmaddr, vsize=vmsize, off=fileoff, size=filesize))
        p += size
    return out


def symtab(data, at):
    """返回 (symoff, nsyms, stroff, strsize) 或 None"""
    ncmds, = struct.unpack_from("<I", data, at + 16)
    p = at + 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", data, p)
        if cmd == 0x2:
            return struct.unpack_from("<4I", data, p + 8)
        p += size
    return None


def global_symbols(data, at):
    """提取全局（N_EXT 且已定义）符号名集合"""
    st = symtab(data, at)
    if not st:
        return None
    symoff, nsyms, stroff, strsize = st
    names = set()
    for i in range(nsyms):
        o = symoff + i * 16
        if o + 16 > len(data):
            break
        strx, ntype, sect, desc, value = struct.unpack_from("<IBBHQ", data, o)
        if not (ntype & 0x01):        # N_EXT
            continue
        if (ntype & 0x0E) == 0:        # N_UNDF
            continue
        if value == 0:
            continue
        end = data.find(b"\0", stroff + strx)
        if end < 0:
            continue
        try:
            names.add(data[stroff + strx:end].decode("latin1"))
        except Exception:
            pass
    return names


def find_kext_macho(data, kc_kernel_off, bundle_id):
    """在 KC 里找某个 bundle 的 Mach-O：用 __PRELINK_INFO 里的加载地址匹配段 vmaddr"""
    ksegs = segments(data, kc_kernel_off)
    info = next((s for s in ksegs if s["name"] == "__PRELINK_INFO"), None)
    if not info:
        return None
    blob = data[info["off"]:info["off"] + info["size"]]
    a = blob.find(b"<dict>")
    b = blob.rfind(b"</dict>")
    text = blob[a:b].decode("utf-8", "replace")
    m = re.search(r"<key>CFBundleIdentifier</key>\s*<string>" + re.escape(bundle_id) +
                  r"</string>.*?<key>_PrelinkExecutableLoadAddr</key>\s*<integer[^>]*>([^<]*)</integer>",
                  text, re.S)
    if not m:
        return None
    addr = int(m.group(1).strip(), 0) if m.group(1).strip() else 0
    if not addr:
        return None
    # 找 vmaddr == addr 且含 __TEXT 的 Mach-O 头
    pos = kc_kernel_off
    while True:
        pos = data.find(b"\xcf\xfa\xed\xfe", pos)
        if pos < 0:
            return None
        segs = segments(data, pos)
        if segs and segs[0]["va"] == addr:
            return pos
        pos += 4


def main() -> int:
    print("加载 Apple kernelcache ...")
    kc = load_kc()

    print("解析 Apple 内核符号表 ...")
    apple_syms = global_symbols(kc, KC_HEADER_OFF)
    if apple_syms is None:
        print("  Apple 内核没有 LC_SYMTAB，改用导出表（暂不支持）")
        return 1
    print(f"  Apple 内核导出符号: {len(apple_syms):,}")

    print("解析我们内核符号表 ...")
    ours = io.open(OURS, "rb").read()
    our_syms = global_symbols(ours, 0)
    if our_syms is None:
        print("  我们的内核没有 LC_SYMTAB")
        return 1
    print(f"  我们的内核导出符号: {len(our_syms):,}")

    missing = apple_syms - our_syms
    extra = our_syms - apple_syms
    print(f"\n  Apple 有而我们没有 : {len(missing):,}")
    print(f"  我们有而 Apple 没有 : {len(extra):,}")

    # APFS kext 的导入符号（如果它有 symtab）
    print("\n定位 APFS kext ...")
    apfs_off = find_kext_macho(kc, KC_HEADER_OFF, "com.apple.filesystems.apfs")
    if apfs_off is None:
        print("  没找到 APFS kext 的 Mach-O")
    else:
        segs = segments(kc, apfs_off)
        print(f"  找到 @0x{apfs_off:x}，段: {', '.join(s['name'] for s in segs[:5])}")
        st = symtab(kc, apfs_off)
        if st:
            symoff, nsyms, stroff, strsize = st
            undef = set()
            for i in range(nsyms):
                o = symoff + i * 16
                strx, ntype, sect, desc, value = struct.unpack_from("<IBBHQ", kc, o)
                if (ntype & 0x01) and (ntype & 0x0E) == 0:
                    end = kc.find(b"\0", stroff + strx)
                    undef.add(kc[stroff + strx:end].decode("latin1"))
            print(f"  APFS 未定义符号: {len(undef):,}")
            bad = undef & missing
            print(f"  其中我们内核缺的: {len(bad):,}")
            for s in sorted(bad)[:25]:
                print("    " + s)
        else:
            print("  APFS 是预链接镜像，没有 symtab（无法直接取导入表）")

    print("\n=== Apple 有而我们没有的符号（按前缀统计，前 20）===")
    from collections import Counter
    c = Counter()
    for s in missing:
        key = s.split("_")[1] if s.startswith("_") and "_" in s[1:] else s[:12]
        c[key] += 1
    for k, v in c.most_common(20):
        print(f"  {k:<28} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
