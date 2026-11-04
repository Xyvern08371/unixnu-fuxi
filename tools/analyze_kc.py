#!/usr/bin/env python3
"""解析 Apple KernelCollection（magic 0xbebafeca）容器：找出内核和各 kext 的 Mach-O。

只读分析，不导出任何 Apple 二进制。
"""

import io
import struct
import sys
import zipfile

IPSW = r"E:\download\iPhone10,3,iPhone10,6_16.7.16_20H392_Restore.ipsw"
ENTRY = "kernelcache.release.iphone10b"


def load_payload() -> bytes:
    import lzfse
    with zipfile.ZipFile(IPSW) as z:
        raw = z.read(ENTRY)
    # DER 包装
    i = 2 if raw[1] & 0x80 else 1
    ln = raw[1]
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


def main() -> int:
    data = load_payload()
    print(f"KC 容器: {len(data):,} 字节")

    magic, version, flags = struct.unpack_from("<III", data, 0)
    print(f"  magic=0x{magic:08x} version={version} flags=0x{flags:x}")

    # KC v1 头：magic, version, flags, ... 具体布局随版本变化，这里直接扫描 Mach-O
    print("\n=== 扫描内部 Mach-O 头（0xfeedfacf）===")
    hits = []
    pos = 0
    while True:
        pos = data.find(b"\xcf\xfa\xed\xfe", pos)
        if pos < 0:
            break
        cpu, sub, kind, ncmds, sizeofcmds, flags2 = struct.unpack_from("<iiIIII", data, pos + 4)
        if cpu == 0x0100000C and kind in (2, 0xB, 6, 8):   # arm64, EXECUTE/DYLIB/BUNDLE
            hits.append((pos, kind, ncmds, sizeofcmds))
        pos += 4
    print(f"  找到 {len(hits)} 个候选 Mach-O 头")

    # 通过 __PRELINK_INFO / 段名判断哪个是内核
    def segs_at(off):
        ncmds, = struct.unpack_from("<I", data, off + 16)
        p = off + 32
        out = []
        for _ in range(ncmds):
            cmd, size = struct.unpack_from("<II", data, p)
            if cmd == 0x19:
                nm = data[p + 8:p + 24].split(b"\0")[0].decode("latin1")
                vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<4Q", data, p + 24)
                out.append((nm, vmaddr, vmsize, fileoff, filesize))
            p += size
        return out

    kernel = None
    for off, kind, ncmds, sizeofcmds in hits:
        names = [s[0] for s in segs_at(off)]
        if "__PRELINK_INFO" in names or "__PRELINK_TEXT" in names:
            kernel = (off, names)
            break
    if kernel:
        off, names = kernel
        print(f"\n=== 内核 Mach-O 在偏移 0x{off:x} ===")
        for nm, va, vs, fo, fs in segs_at(off):
            print(f"  {nm:<20} va=0x{va:012x} vsize=0x{vs:>9x} file=0x{fo:>9x}/{fs:,}")
    else:
        print("\n  没找到带 __PRELINK_* 段的 Mach-O（KC 布局可能不同）")

    print("\n=== 关键字符串定位 ===")
    for s in (b"com.apple.kernel", b"com.apple.filesystems.apfs", b"AppleAPFS",
              b"com.apple.driver.AppleKeyStore", b"Darwin Kernel Version"):
        i = data.find(s)
        print(f"  {s.decode():<40} {'偏移 0x%x' % i if i >= 0 else '没有'}")

    i = data.find(b"xnu-8796")
    if i < 0:
        i = data.find(b"xnu-")
    if i >= 0:
        j = data.find(b"\0", i)
        print(f"\n  版本字符串: {data[i:j if j > 0 else i + 60].decode('latin1', 'replace')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
