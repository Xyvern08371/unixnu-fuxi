#!/usr/bin/env python3
"""find_probe.py -- 检查探针驱动是否真的进了固件

原理: 每个 UEFI 固件卷里的文件都以 16 字节 GUID 开头。探针的 FILE_GUID 是
9c4e2a71-3d85-4f0b-8a6e-1b7d5c2e9f34, 在固件里搜这个字节序列即可确定它在不在。
注意 EFI GUID 的前三个字段是小端。

用法: python find_probe.py boot-fuxi.img
返回码: 0 = 找到, 1 = 没找到
"""
from __future__ import annotations

import struct
import sys
import uuid
import zlib

PROBE_GUID = "9c4e2a71-3d85-4f0b-8a6e-1b7d5c2e9f34"


def guid_bytes(text: str) -> bytes:
    g = uuid.UUID(text)
    return struct.pack("<IHH", g.time_low, g.time_mid, g.time_hi_version) + g.bytes[8:]


def payload_of(path: str) -> bytes:
    """boot.img 的 kernel 段; 如果是 gzip 就解开。"""
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:8] != b"ANDROID!":
        return data
    page, = struct.unpack_from("<I", data, 36)
    ksize, = struct.unpack_from("<I", data, 8)
    blob = data[page:page + ksize]
    if blob[:2] == b"\x1f\x8b":
        try:
            return zlib.decompressobj(31).decompress(blob)
        except zlib.error:
            return blob
    return blob


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("用法: python find_probe.py <boot-fuxi.img>", file=sys.stderr)
        return 2
    path = argv[0]
    try:
        raw = payload_of(path)
    except OSError as exc:
        print("打不开 %s: %s" % (path, exc), file=sys.stderr)
        return 2

    hit = raw.find(guid_bytes(PROBE_GUID))
    print("%s: 固件 %d 字节, %d 个固件卷" % (path, len(raw), raw.count(b"_FVH")))
    if hit >= 0:
        print("  探针 GUID %s: FOUND @ 0x%x" % (PROBE_GUID, hit))
        return 0
    print("  探针 GUID %s: MISSING" % PROBE_GUID)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
