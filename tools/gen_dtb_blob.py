#!/usr/bin/env python3
"""把 .dtb 转成 C 数组源码，供驱动内嵌使用。

用法: python3 tools/gen_dtb_blob.py <输入.dtb> <输出.c>

生成内容:
    const UINT8  gFuxiDtb[]   = { 0xd0, 0x0d, ... };
    const UINT32 gFuxiDtbSize = 123456;

这样即使固件没有把设备树放进 EFI 配置表，我们也能把一份有效设备树
交给"内核"（内核启动时 x0 指向它）。
"""

import sys
from pathlib import Path

PER_LINE = 16


def main() -> int:
    if len(sys.argv) != 3:
        print("用法: gen_dtb_blob.py <输入.dtb> <输出.c>")
        return 2

    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    data = src.read_bytes()

    if len(data) < 8 or data[0:4] != b"\xd0\x0d\xfe\xed":
        print(f"警告: {src} 开头不是 DTB 魔数 D00DFEED，仍然继续")

    out = []
    out.append("/* 自动生成，不要手改。来源: %s (%d 字节) */" % (src.name, len(data)))
    out.append("")
    out.append('#include <Uefi.h>')
    out.append("")
    out.append("CONST UINT8  gFuxiDtbData[] = {")
    for i in range(0, len(data), PER_LINE):
        chunk = data[i:i + PER_LINE]
        out.append("  " + ", ".join("0x%02x" % b for b in chunk) + ",")
    out.append("};")
    out.append("")
    out.append("CONST UINT32 gFuxiDtbSize = 0x%x;    /* %d 字节 */" % (len(data), len(data)))
    out.append("")

    dst.write_text("\n".join(out), encoding="utf-8")
    print(f"已生成 {dst}  ({len(data)} 字节 -> {dst.stat().st_size} 字节源码)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
