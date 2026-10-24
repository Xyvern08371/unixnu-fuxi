#!/usr/bin/env python3
"""用 UniXNU 的 prelink 规划逻辑，跑一次真实的组件绑定（不做写入）。

输入：
  · 我们编译的内核（xnu-8796.101.5，16K 页）
  · Apple kernelcache 归一化后的内核镜像（xnu-8796.142.1）
输出：plan() 的结果或它抛出的第一个错误 —— 这就是绑定可行性的实测答案。
"""

import io
import struct
import sys
import zipfile

sys.path.insert(0, r"E:\download\UniXNU\kits\NativePrelink")

IPSW = r"E:\download\iPhone10,3,iPhone10,6_16.7.16_20H392_Restore.ipsw"
ENTRY = "kernelcache.release.iphone10b"
OURS = r"E:\download\xnu-kernel-21\out\kernel.development.fuxi"
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


def normalize(img: bytearray) -> bytearray:
    """把 __PRELINK_INFO 里的裸 plist 片段补成合法 XML，便于解析器读取"""
    ncmds, = struct.unpack_from("<I", img, 16)
    p = 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", img, p)
        if cmd == 0x19:
            name = img[p + 8:p + 24].split(b"\0")[0]
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<4Q", img, p + 24)
            if name == b"__PRELINK_INFO":
                blob = bytes(img[fileoff:fileoff + filesize])
                a = blob.find(b"<dict>")
                b = blob.rfind(b"</dict>")
                frag = blob[a:b + len(b"</dict>")]
                # 他们的解析器要求根元素是 <dict>，不要 <plist> 包装
                xml = b'<?xml version="1.0" encoding="UTF-8"?>' + frag
                if len(xml) > filesize:
                    raise SystemExit("XML 比段还大，无法原地替换")
                img[fileoff:fileoff + filesize] = xml + b"\0" * (filesize - len(xml))
                return img
        p += size
    raise SystemExit("没找到 __PRELINK_INFO")


def main() -> int:
    import native_prelink as np

    print("加载并归一化 Apple kernelcache ...")
    kc = load_kc()
    original = normalize(bytearray(kc[KC_KERNEL_OFF:]))

    print("加载我们编译的内核 ...")
    native = bytearray(io.open(OURS, "rb").read())
    # 我们的构建带 __CTF 调试段（filesize>0, vsize=0），校验过不去；等价于他们的 noctf 版本
    ncmds, = struct.unpack_from("<I", native, 16)
    p = 32
    for _ in range(ncmds):
        cmd, length = struct.unpack_from("<II", native, p)
        if cmd == 0x19 and length >= 72:
            name = bytes(native[p + 8:p + 24]).split(b"\\0")[0]
            if name == b"__CTF":
                # __CTF：整段清零（vmsize/fileoff/filesize + 各 section 的 addr/size），
                # 等价于他们的 noctf 构建；否则 section 会落在段外，校验失败
                struct.pack_into("<Q", native, p + 32, 0)   # vmsize
                struct.pack_into("<Q", native, p + 40, 0)   # fileoff
                struct.pack_into("<Q", native, p + 48, 0)   # filesize
                nsects, = struct.unpack_from("<I", native, p + 64)
                for si in range(nsects):
                    sp = p + 72 + si * 80
                    struct.pack_into("<Q", native, sp + 32, 0)   # addr
                    struct.pack_into("<Q", native, sp + 40, 0)   # size
                    struct.pack_into("<I", native, sp + 48, 0)   # offset
                print("  已屏蔽 __CTF 段")
        p += length
    native = bytes(native)

    roots = ["com.apple.filesystems.apfs"]
    slide = -0x1000000

    print(f"规划: roots={roots} slide={slide:#x}")
    try:
        result = np.plan(native, bytes(original), roots, slide)
    except Exception as e:
        print("\n❌ plan() 失败:")
        print("   " + type(e).__name__ + ": " + str(e))
        return 1

    print("\n✅ plan() 成功")
    print(f"  组件数      : {len(result['components'])}")
    print(f"  无代码组件  : {len(result['codeless_components'])}")
    print(f"  内核接口    : {len(result['kernel_interfaces'])}")
    print(f"  指针绑定    : {result['pointer_counts']}")
    print(f"  段范围数    : {len(result['extents'])}")
    print("\n  选中的组件（前 30）:")
    for c in result["components"][:30]:
        print("    " + c)
    if len(result["components"]) > 30:
        print(f"    ... 还有 {len(result['components']) - 30} 个")
    return 0


if __name__ == "__main__":
    sys.exit(main())
