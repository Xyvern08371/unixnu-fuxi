#!/usr/bin/env python3
"""原地替换 boot.img 的内核，但**保留 gzip 流之后的内容**（里面是 DTB 等）。

fuxi 的 boot.img 里，kernel 段 = [gzip 内核][DTB][填充]，header 的 kernel_size
覆盖了这三部分。所以替换内核时必须把 DTB 跟着搬过去。

用法: patch_boot_kernel.py <原始 boot.img> <新内核.gz> <输出 boot.img>
"""

import hashlib
import struct
import sys
import zlib


def gzip_stream_len(gz: bytes) -> int:
    """返回 gzip 流实际占用的字节数（不含后面的 DTB/填充）"""
    d = zlib.decompressobj(31)
    d.decompress(gz)
    return len(gz) - len(d.unused_data)


def main() -> int:
    src, newk, dst = sys.argv[1], sys.argv[2], sys.argv[3]

    d = open(src, "rb").read()
    ks, = struct.unpack_from("<I", d, 8)
    pg, = struct.unpack_from("<I", d, 36)
    rs, = struct.unpack_from("<I", d, 16)

    region = d[pg:pg + ks]
    used = gzip_stream_len(region)
    tail = region[used:]           # DTB + 填充
    print(f"原始: {len(d):,} 字节 page={pg} kernel_region={ks:,} (gzip {used:,} + 尾部 {len(tail):,})")
    print(f"  尾部开头 16 字节: {tail[:16].hex()}")

    k = open(newk, "rb").read()
    print(f"新内核: {len(k):,} 字节")

    out = bytearray(d[:pg]) + k + tail
    out += b"\0" * ((-len(out)) % pg)

    new_ks = len(k) + len(tail)
    struct.pack_into("<I", out, 8, new_ks)
    print(f"新 kernel_size = {new_ks:,}（内核 + 尾部）")

    # id = sha1(kernel 区域 + ramdisk + second)
    sha = hashlib.sha1()
    sha.update(bytes(out[pg:pg + new_ks]))
    if rs:
        sha.update(bytes(out[pg + new_ks:pg + new_ks + rs]))
    out[576:596] = sha.digest()
    out[596:608] = b"\0" * 12

    open(dst, "wb").write(bytes(out))
    print(f"输出: {len(out):,} 字节 -> {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
