#!/usr/bin/env python3
"""分析 IPSW 里的 kernelcache：版本、PRELINK 组件、是否含 APFS。

只做只读分析（内存里解析，不导出 Apple 二进制到磁盘）。
"""

import io
import plistlib
import struct
import sys
import zipfile

IPSW = r"E:\download\iPhone10,3,iPhone10,6_16.7.16_20H392_Restore.ipsw"
ENTRY = "kernelcache.release.iphone10b"


def der_items(buf, start, end):
    """极简 DER 解析：返回 (tag, 内容) 列表"""
    items = []
    i = start
    while i < end:
        tag = buf[i]
        i += 1
        if i >= end:
            break
        ln = buf[i]
        i += 1
        if ln & 0x80:
            n = ln & 0x7F
            ln = int.from_bytes(buf[i:i + n], 'big')
            i += n
        items.append((tag, buf[i:i + ln]))
        i += ln
    return items


def im4p_payload(blob: bytes):
    """支持两种封装：裸 IM4P，或 DER SEQUENCE{IA5String,IA5String,IA5String,OCTET STRING}"""
    if blob[:4] == b"IM4P":
        header_len, = struct.unpack_from(">I", blob, 4)
        typ = blob[8:12].decode("latin1")
        return typ, blob[12:header_len], blob[header_len:]

    # DER
    assert blob[0] == 0x30, blob[:4].hex()
    i = 1
    ln = blob[i]; i += 1
    if ln & 0x80:
        n = ln & 0x7F
        total = int.from_bytes(blob[i:i + n], 'big')
        i += n
    else:
        total = ln
    items = der_items(blob, i, i + total)
    typ = items[0][1].decode('latin1', 'replace') if items else '?'
    desc = items[2][1].decode('latin1', 'replace') if len(items) > 2 else ''
    payload = next(v for tag, v in items if tag == 0x04)   # 第一个 OCTET STRING 才是内容
    return typ, desc.encode(), payload


def main() -> int:
    with zipfile.ZipFile(IPSW) as z:
        raw = z.read(ENTRY)
    print(f"kernelcache: {len(raw):,} 字节")

    typ, header, payload = im4p_payload(raw)
    print(f"  IM4P 类型 = {typ!r}，header = {len(header)} 字节")
    print(f"  payload   = {len(payload):,} 字节，开头 {payload[:8].hex()}")

    data = payload
    if payload[:4] in (b"bvx2", b"bvxn", b"bvx$", b"bvx1", b"bvx-"):
        import lzfse
        data = lzfse.decompress(payload)
        print(f"  LZFSE 解压后 = {len(data):,} 字节")
    else:
        print("  不是 LZFSE（可能是未压缩或加密）")

    # 是不是 Mach-O
    magic = struct.unpack_from("<I", data, 0)[0]
    print(f"  magic = 0x{magic:08x} ({'Mach-O 64' if magic == 0xfeedfacf else '非 Mach-O'})")
    if magic != 0xfeedfacf:
        return 1

    ncmds, = struct.unpack_from("<I", data, 16)
    sizeofcmds, = struct.unpack_from("<I", data, 20)
    print(f"  load commands: {ncmds} 个，{sizeofcmds:,} 字节")

    # 段列表
    off = 32
    segs = []
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from("<II", data, off)
        if cmd == 0x19:
            name = data[off + 8:off + 24].split(b"\0")[0].decode("latin1")
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<4Q", data, off + 24)
            segs.append((name, vmaddr, vmsize, fileoff, filesize))
        off += cmdsize

    print("\n  段:")
    for name, va, vs, fo, fs in segs:
        print(f"    {name:<20} va=0x{va:012x} size=0x{vs:>9x} file=0x{fo:>9x}/{fs:,}")

    # 版本字符串
    print("\n  版本字符串:")
    for pat in (b"Darwin Kernel Version", b"xnu-8796", b"RELEASE_ARM64"):
        i = data.find(pat)
        if i >= 0:
            chunk = data[i:i + 160]
            if pat == b"xnu-8796":
                j = chunk.find(b"\0")
                chunk = chunk[:j if j > 0 else 80]
            else:
                j = chunk.find(b"\0")
                chunk = chunk[:j if j > 0 else 120]
            print(f"    {pat.decode()}: {chunk.decode('latin1', 'replace')}")

    # PRELINK_INFO（kext 清单）
    info = next((s for s in segs if s[0] == "__PRELINK_INFO"), None)
    if not info:
        print("\n  没有 __PRELINK_INFO 段")
        return 0

    name, va, vs, fo, fs = info
    blob = data[fo:fo + fs]
    # 里面是 XML plist，找 <?xml 到 </plist>
    a = blob.find(b"<?xml")
    b = blob.find(b"</plist>")
    if a < 0 or b < 0:
        print("  __PRELINK_INFO 里没找到 XML plist")
        return 0

    pl = plistlib.loads(blob[a:b + len(b"</plist>")])
    entries = pl.get("_PrelinkInfoDictionary") or pl.get("_PrelinkExecutableList") or []
    print(f"\n  __PRELINK_INFO: {len(entries)} 个组件")
    ids = []
    for e in entries:
        bid = e.get("CFBundleIdentifier") or e.get("_PrelinkBundlePath") or "?"
        ids.append(str(bid))
    for bid in sorted(ids)[:40]:
        print("    " + bid)
    if len(ids) > 40:
        print(f"    ... 还有 {len(ids) - 40} 个")

    keys = ("appleapfs", "apfs", "keystore", "sep", "hfs")
    print("\n  关注的组件:")
    for k in keys:
        hit = [i for i in ids if k in i.lower()]
        print(f"    {k:<12} {'有: ' + ', '.join(hit[:4]) if hit else '没有'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
