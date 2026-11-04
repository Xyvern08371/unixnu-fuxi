"""把 XNU payload 做成可刷进 dtbo 分区的裸镜像。

格式（放在分区起始）：
    offset 0   magic "FUXIPAY1"   (8 字节)
    offset 8   u64 长度（小端）
    offset 16  payload 数据
    末尾补零到 16MB（方便 fastboot 对齐，也避免读到旧数据）
"""

import io
import struct
import sys

MAGIC = b"FUXIPAY1"
PAD_TO = 16 * 1024 * 1024


def main() -> int:
    if len(sys.argv) != 3:
        print("用法: mkpayload_img.py <payload.bin> <out.img>")
        return 2

    src, dst = sys.argv[1], sys.argv[2]
    data = io.open(src, "rb").read()
    out = bytearray()
    out += MAGIC
    out += struct.pack("<Q", len(data))
    out += data
    if len(out) < PAD_TO:
        out += b"\0" * (PAD_TO - len(out))
    io.open(dst, "wb").write(out)
    print(f"{dst}: magic + {len(data):,} 字节 payload -> {len(out):,} 字节镜像")
    return 0


if __name__ == "__main__":
    sys.exit(main())
