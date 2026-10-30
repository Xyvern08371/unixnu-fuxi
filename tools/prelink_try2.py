#!/usr/bin/env python3
"""prelink 绑定实测：收集 APFS 需要的全部内核符号里我们缺的。

策略：
  · 用容错 Mach-O 解析（Apple 预链接 kext 头部有裁剪）
  · 把 unique_kernel_binding 换成"记录 + 占位"版本，让 plan() 不被第一个缺失符号打断
  · 最后输出完整缺失清单（这些用兼容 shim 补即可）
"""

import io
import struct
import sys
import zipfile

sys.path.insert(0, r"E:\download\UniXNU\kits\NativePrelink")

IPSW = r"E:\download\iPhone10,3,iPhone10,6_16.7.16_20H392_Restore.ipsw"
ENTRY = "kernelcache.release.iphone10b"
OURS = r"E:\download\xnu-kernel-22\out\kernel.development.fuxi"
KC_KERNEL_OFF = 0x1C


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


def normalize_info(img: bytearray) -> bytearray:
    ncmds, = struct.unpack_from("<I", img, 16)
    p = 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", img, p)
        if cmd == 0x19:
            name = bytes(img[p + 8:p + 24]).split(b"\0")[0]
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<4Q", img, p + 24)
            if name == b"__PRELINK_INFO":
                blob = bytes(img[fileoff:fileoff + filesize])
                a = blob.find(b"<dict>")
                b = blob.rfind(b"</dict>")
                frag = blob[a:b + len(b"</dict>")]
                xml = b'<?xml version="1.0" encoding="UTF-8"?>' + frag
                img[fileoff:fileoff + filesize] = xml + b"\0" * (filesize - len(xml))
                return img
        p += size
    raise SystemExit("no __PRELINK_INFO")


def strip_ctf(data: bytearray) -> bytearray:
    ncmds, = struct.unpack_from("<I", data, 16)
    p = 32
    for _ in range(ncmds):
        cmd, length = struct.unpack_from("<II", data, p)
        if cmd == 0x19 and length >= 72:
            if bytes(data[p + 8:p + 24]).split(b"\0")[0] == b"__CTF":
                struct.pack_into("<Q", data, p + 32, 0)
                struct.pack_into("<Q", data, p + 40, 0)
                struct.pack_into("<Q", data, p + 48, 0)
                nsects, = struct.unpack_from("<I", data, p + 64)
                for si in range(nsects):
                    sp = p + 72 + si * 80
                    struct.pack_into("<Q", data, sp + 32, 0)
                    struct.pack_into("<Q", data, sp + 40, 0)
                    struct.pack_into("<I", data, sp + 48, 0)
        p += length
    return data


def tolerant_macho(data, at=0):
    if at < 0 or at + 32 > len(data):
        raise ValueError("Mach-O header outside image")
    magic, cpu, subtype, kind, count, size = struct.unpack_from("<6I", data, at)
    if (magic, cpu, subtype) != (0xfeedfacf, 0x100000C, 0):
        raise ValueError("Only ordinary little-endian ARM64 is supported")
    end = min(at + 32 + size, len(data))
    offset = at + 32
    commands, segments = [], []
    for _ in range(count):
        if offset + 8 > end:
            break
        command, length = struct.unpack_from("<II", data, offset)
        if length < 8 or length % 8 or offset + length > end:
            break
        commands.append((command, offset, length))
        if command == 0x19 and length >= 72:
            name, va, vsize, fileoff, filesize, mp, ip, nsects, flags = \
                struct.unpack_from("<16s4Q4I", data, offset + 8)
            seg = dict(name=name.rstrip(b"\0").decode(), va=va, size=vsize,
                       fileoff=fileoff, filesize=filesize, command_offset=offset,
                       maxprot=mp, initprot=ip, sections=[])
            for index in range(nsects):
                sa = offset + 72 + index * 80
                if sa + 80 > offset + length:
                    break
                sname, _, addr, extent, soff = struct.unpack_from("<16s16sQQI", data, sa)
                seg["sections"].append(dict(name=sname.rstrip(b"\0").decode(),
                                            va=addr, size=extent, fileoff=soff))
            segments.append(seg)
        offset += length
    return {"kind": kind, "segments": segments, "commands": commands}


def main() -> int:
    import native_prelink as np
    np.macho = tolerant_macho

    print("加载并归一化 Apple kernelcache ...")
    kc = load_kc()
    original = bytes(normalize_info(bytearray(kc[KC_KERNEL_OFF:])))

    print("加载我们的内核 ...")
    native = bytes(strip_ctf(bytearray(io.open(OURS, "rb").read())))

    # plan() 会校验绑定目标必须落在内核某个段里，所以占位地址取我们 __TEXT 的起始
    nm = tolerant_macho(native)
    placeholder = next(s["va"] for s in nm["segments"] if s["name"] == "__TEXT")

    missing = {}
    orig_ukb = np.unique_kernel_binding

    def collecting_binding(address, original_exports, native_by_name):
        names = original_exports.get(address, [])
        choices = {new for name in names for new in native_by_name.get(name, set())}
        if len(choices) == 1:
            return next(iter(choices))
        for name in names:
            missing.setdefault(name, address)
        return placeholder          # 合法占位，让 plan() 继续收集

    np.unique_kernel_binding = collecting_binding

    result = None
    try:
        result = np.plan(native, original, ["com.apple.filesystems.apfs"], -0x1000000)
        print("\n✅ plan() 全程通过")
    except Exception as e:
        print(f"\n⚠ plan() 在别处中断: {type(e).__name__}: {e}")

    if result:
        print(f"  组件: {len(result['components'])}  无代码: {len(result['codeless_components'])}"
              f"  内核接口: {len(result['kernel_interfaces'])}")
        print(f"  指针绑定: {result['pointer_counts']}")

    print(f"\n缺失的内核符号: {len(missing)} 个")
    for name, addr in sorted(missing.items()):
        print("    %-52s 0x%x" % (name, addr))
    return 0


if __name__ == "__main__":
    sys.exit(main())
