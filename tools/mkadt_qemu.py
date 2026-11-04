#!/usr/bin/env python3
"""生成给 QEMU 用的 ADT（GIC 用 QEMU virt 地址，DRAM 落在 QEMU 的 RAM 里）。

QEMU virt 的 RAM 从 0x40000000 开始，所以 dram-base 设成 0x40000000，
不能沿用真机的 0x100000000。

用法: mkadt_qemu.py <输出.adt> [--dump]
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iosadt as adt        # noqa: E402
import mkadt_fuxi as M      # noqa: E402

DRAM_BASE = 0x42000000   # 32MB 对齐，避开 QEMU 的 DTB
DRAM_SIZE = 0x7E000000      # 到 0xC0000000，把帧缓冲 0xB0000000 包进来


def patch_u64(blob, old, new):
    b = bytearray(blob)
    n = 0
    for i in range(0, len(b) - 8 + 1):
        v, = struct.unpack_from("<Q", b, i)
        if v == old:
            struct.pack_into("<Q", b, i, new)
            n += 1
    return bytes(b), n


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    out = sys.argv[1]

    root = M.build(qemu=True)          # GIC/定时器用 QEMU 的值
    blob = adt.serialize(root)

    # 把 dram 改到 QEMU 的 RAM 里
    blob, n1 = patch_u64(blob, M.PHYS_BASE, DRAM_BASE)
    blob, n2 = patch_u64(blob, M.MEM_SIZE, DRAM_SIZE)
    print(f"dram 替换: base {n1} 处, size {n2} 处 -> {DRAM_BASE:#x}/{DRAM_SIZE:#x}")

    open(out, "wb").write(blob)
    print(f"输出: {out}  {len(blob):,} 字节")

    if "--dump" in sys.argv:
        r, _ = adt.parse(blob)
        adt.dump(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
