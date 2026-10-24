#!/usr/bin/env python3
"""打包 fuxi 的 boot.img（header v1，page 2048，kernel 段 = gzip内核 + DTB）。

fuxi 的原厂/CI 镜像布局（实测）：

    [header 2048][ gzip 内核 ][ DTB ][ 填充 ]
                 └────── kernel_size 覆盖这一段 ──────┘

ABL 在缺 DTB 时会拒绝启动，所以 DTB 必须跟在内核后面、算在 kernel_size 里。
"""

import argparse
import hashlib
import struct
import sys

PAGE = 2048
KERNEL_ADDR = 0x10000000
RAMDISK_ADDR = 0x10000000
TAGS_ADDR = 0x10000000
OS_VERSION = 0x1A00016B


def pad(data: bytes, page: int) -> bytes:
    rem = len(data) % page
    return data if rem == 0 else data + b"\0" * (page - rem)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kernel", required=True, help="gzip 压缩的内核 Image")
    ap.add_argument("--dtb", required=True, help="设备树（跟在 gzip 后面）")
    ap.add_argument("--output", required=True)
    ap.add_argument("--cmdline", default="")
    a = ap.parse_args()

    kernel = open(a.kernel, "rb").read()
    dtb = open(a.dtb, "rb").read()

    if kernel[:3] != b"\x1f\x8b\x08":
        print("警告：内核不是 gzip，fuxi 的 ABL 可能不接受", file=sys.stderr)

    region = pad(kernel + dtb, PAGE)
    print(f"kernel     : {len(kernel):>10,} bytes (gzip)")
    print(f"dtb        : {len(dtb):>10,} bytes")
    print(f"kernel_size: {len(region):>10,} bytes（内核 + DTB + 填充）")

    ramdisk = b"\0"
    ident = hashlib.sha1(region + ramdisk).digest()

    cmdline = a.cmdline.encode() + b"\0"
    hdr = struct.pack(
        "<8s10I16s512s32s1024s",
        b"ANDROID!",
        len(region),
        KERNEL_ADDR,
        len(ramdisk),
        RAMDISK_ADDR,
        0,
        0,
        TAGS_ADDR,
        PAGE,
        1,
        OS_VERSION,
        b"\0" * 16,
        cmdline.ljust(512, b"\0"),
        ident + b"\0" * 12,
        b"\0" * 1024,
    )
    hdr = hdr.ljust(PAGE, b"\0")

    out = hdr + region + pad(ramdisk, PAGE)
    open(a.output, "wb").write(out)
    print(f"boot.img   : {len(out):>10,} bytes -> {a.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
