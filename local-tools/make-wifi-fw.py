#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 WFW1 固件容器（写入 fuxi 的 oops 分区，供 WifiProbe.cpp findFirmware() 读取）。

格式（WifiProbe.cpp L391-416 权威）:
  offset 0:  'WFW1' (4 bytes)
  offset 4:  count  (u32 LE)
  offset 8:  count × 32 字节条目: name[24] + offset(u32 LE) + size(u32 LE)
  之后 4KB 对齐，紧跟各固件数据；amss.bin 的 offset 必须 4KB 对齐。

用法: make-wifi-fw.py <out.bin> --amss amss.bin [--amss2 amss2.bin]
"""
import argparse, struct, sys

MAGIC = b'WFW1'
ALIGN = 4096

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--amss', required=True)
    ap.add_argument('--amss2')
    a = ap.parse_args()

    files = [('amss.bin', a.amss)]
    if a.amss2:
        files.append(('amss2.bin', a.amss2))

    data = [open(p, 'rb').read() for _, p in files]
    header_size = 8 + 32 * len(files)
    data_start = (header_size + ALIGN - 1) & ~(ALIGN - 1)

    out = bytearray(data_start)
    out[0:4] = MAGIC
    struct.pack_into('<I', out, 4, len(files))
    cur = data_start
    for i, ((name, _), d) in enumerate(zip(files, data)):
        e = 8 + 32 * i
        out[e:e + len(name)] = name.encode('ascii')
        struct.pack_into('<II', out, e + 24, cur, len(d))
        out[cur:cur + len(d)] = d
        cur += len(d)
        cur = (cur + ALIGN - 1) & ~(ALIGN - 1)

    open(a.out, 'wb').write(out)
    print('WFW1 container: %s  %d B, %d entries' % (a.out, len(out), len(files)))
    for i, ((name, p), d) in enumerate(zip(files, data)):
        off = struct.unpack_from('<I', out, 8 + 32 * i + 24)[0]
        print('  %-12s offset=%#x size=%d' % (name, off, len(d)))
    return 0

if __name__ == '__main__':
    sys.exit(main())
