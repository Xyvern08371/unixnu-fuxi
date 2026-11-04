#!/usr/bin/env python3
"""把任意二进制文件转成 C 数组源码（供固件内嵌）。

用法: python3 tools/gen_blob.py <输入文件> <输出.c> <符号前缀>

生成:
    const UINT8  <前缀>Data[] = { ... };
    const UINT32 <前缀>Size   = N;

例: gen_blob.py kernel.bin kernel_blob.c gKernel
    -> gKernelData[] / gKernelSize
"""

import sys
from pathlib import Path

PER_LINE = 16


def main() -> int:
    if len(sys.argv) != 4:
        print("用法: gen_blob.py <输入文件> <输出.c> <符号前缀>")
        return 2

    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    sym = sys.argv[3]
    data = src.read_bytes()

    out = [
        "/* 自动生成，不要手改。来源: %s (%d 字节) */" % (src.name, len(data)),
        "",
        "#include <Uefi.h>",
        "",
        "CONST UINT8  %sData[] = {" % sym,
    ]
    for i in range(0, len(data), PER_LINE):
        chunk = data[i:i + PER_LINE]
        out.append("  " + ", ".join("0x%02x" % b for b in chunk) + ",")
    out.append("};")
    out.append("")
    out.append("CONST UINT32 %sSize = 0x%x;    /* %d 字节 */" % (sym, len(data), len(data)))
    out.append("")

    dst.write_text("\n".join(out), encoding="utf-8")
    print("%s: %d 字节 -> %s" % (src.name, len(data), dst))
    return 0


if __name__ == "__main__":
    sys.exit(main())
