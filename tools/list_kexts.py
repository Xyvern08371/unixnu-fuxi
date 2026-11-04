#!/usr/bin/env python3
"""列出 Apple kernelcache 里预链接的组件（kext 清单）。

只读分析：不导出任何 Apple 二进制，只打印 Bundle ID 和段信息。
"""

import plistlib
import struct
import sys
import zipfile

IPSW = r"E:\download\iPhone10,3,iPhone10,6_16.7.16_20H392_Restore.ipsw"
ENTRY = "kernelcache.release.iphone10b"


def load():
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


def segments(data, off):
    ncmds, = struct.unpack_from("<I", data, off + 16)
    p = off + 32
    out = {}
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", data, p)
        if cmd == 0x19:
            nm = data[p + 8:p + 24].split(b"\0")[0].decode("latin1")
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<4Q", data, p + 24)
            out[nm] = (vmaddr, vmsize, fileoff, filesize)
        p += size
    return out


def main() -> int:
    data = load()
    segs = segments(data, 0x1C)
    va, vs, fo, fs = segs["__PRELINK_INFO"]
    blob = data[fo:fo + fs]

    a = blob.find(b"<dict>")
    b = blob.rfind(b"</dict>")
    if a < 0 or b < 0:
        print("没找到 plist 片段")
        return 1
    # Apple 的片段里可能有空 <integer/>，plistlib 会崩，改用正则抽取
    import re
    text = blob[a:b + len(b"</dict>")].decode("utf-8", "replace")

    ids = re.findall(r"<key>CFBundleIdentifier</key>\s*<string>([^<]+)</string>", text)
    addrs = re.findall(r"<key>_PrelinkExecutableLoadAddr</key>\s*<integer[^>]*>([^<]*)</integer>", text)
    sizes = re.findall(r"<key>_PrelinkExecutableSize</key>\s*<integer[^>]*>([^<]*)</integer>", text)

    def num(s):
        s = s.strip()
        if not s:
            return 0
        try:
            return int(s, 16) if s.lower().startswith("0x") else int(s)
        except ValueError:
            return 0

    print(f"预链接组件: {len(ids)} 个\\n")
    rows = []
    for k, bid in enumerate(ids):
        exe = num(addrs[k]) if k < len(addrs) else 0
        size = num(sizes[k]) if k < len(sizes) else 0
        rows.append((bid, exe, size))

    rows.sort()
    for bid, exe, size in rows:
        print(f"  {bid:<58} 0x{exe:012x} {size:>8,}")

    print("\n=== 我们关心的 ===")
    for key in ("apfs", "keystore", "sep", "sandbox", "amfi", "bsd", "uart", "gpio", "i2c", "spi"):
        hit = [r[0] for r in rows if key in r[0].lower()]
        print(f"  {key:<10} {', '.join(hit[:3]) if hit else '—'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
