#!/usr/bin/env python3
"""把 shim Image 里内嵌的 payload 换成新内核编出来的 payload。

shim 的 Image 布局：[代码/数据/栈][payload]（payload 在最后，偏移 _payload_start）
所以直接截断到 payload 偏移、追加新 payload、改 image_size 即可。

用法:
  replace_shim_payload.py <shim Image> <新 payload> <输出 Image>
"""

import struct
import sys

PAYLOAD_OFF = 0x2C000   # _payload_start（shim.ld 里固定）


def main() -> int:
    img_path, payload_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]

    img = bytearray(open(img_path, "rb").read())
    payload = open(payload_path, "rb").read()

    # 校验：原位置上确实是 payload
    if bytes(img[PAYLOAD_OFF:PAYLOAD_OFF + 7]) != b"FUXIXNU":
        print(f"警告：0x{PAYLOAD_OFF:x} 处不是 FUXIXNU（实际 {bytes(img[PAYLOAD_OFF:PAYLOAD_OFF+8])}）",
              file=sys.stderr)

    out = bytearray(img[:PAYLOAD_OFF]) + payload

    # ARM64 Image 头：image_size（偏移 0x10）改成总大小
    struct.pack_into("<Q", out, 0x10, len(out))

    open(out_path, "wb").write(bytes(out))
    print(f"旧 payload 之后截断于 0x{PAYLOAD_OFF:x}，新 payload {len(payload):,} 字节")
    print(f"输出 Image: {len(out):,} 字节 -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
