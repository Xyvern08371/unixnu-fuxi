#!/usr/bin/env python3
"""check_probe.py -- 检查 boot-fuxi.img 里的探针驱动，并判断是哪一版

为什么需要它: 固件卷是 LZMA 压缩的, 直接搜 GUID/字符串永远搜不到(假阴性)。
必须先把 GUID 定义的压缩段解开再找。

用法: python check_probe.py boot-fuxi.img
"""
from __future__ import annotations

import lzma
import struct
import sys
import uuid
import zlib

PROBE_GUID = "9c4e2a71-3d85-4f0b-8a6e-1b7d5c2e9f34"
LZMA_GUID = "ee4e5898-3914-4259-9d6e-dc7bd79403cf"

MARKERS = {
    "v1 (DriverEntry 打印)": "alive inside real UEFI",
    "v2 (EndOfDxe 打印)": "staying here on purpose",
    "v3 (刷 GOP 绿屏)": "memmap-ok",
    "v4 (入口直接 halt)": "fuxi-probe-v4-halt",
    "v5 (定时器轮询 GOP)": "fuxi-probe-v5-timer",
}


def guid_bytes(text: str) -> bytes:
    g = uuid.UUID(text)
    return struct.pack("<IHH", g.time_low, g.time_mid, g.time_hi_version) + g.bytes[8:]


def firmware_payload(path: str) -> bytes:
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:8] != b"ANDROID!":
        return data
    page = struct.unpack_from("<I", data, 36)[0]
    ksize = struct.unpack_from("<I", data, 8)[0]
    blob = data[page:page + ksize]
    if blob[:2] == b"\x1f\x8b":
        return zlib.decompressobj(31).decompress(blob)
    return blob


def walk_lzma_sections(raw: bytes):
    """遍历 GUID-defined (LZMA) 压缩段, 解压后 yield。"""
    needle = guid_bytes(LZMA_GUID)
    pos = 0
    while True:
        i = raw.find(needle, pos)
        if i < 0:
            return
        pos = i + 1
        sec = i - 4
        if sec < 0:
            continue
        size = raw[sec] | (raw[sec + 1] << 8) | (raw[sec + 2] << 16)
        if size <= 0 or sec + size > len(raw):
            continue
        data_off = struct.unpack_from("<H", raw, i + 16)[0]
        try:
            yield lzma.decompress(raw[sec + data_off:sec + size], format=lzma.FORMAT_ALONE)
        except lzma.LZMAError:
            continue


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("用法: python check_probe.py <boot-fuxi.img>", file=sys.stderr)
        return 2

    raw = firmware_payload(argv[0])
    print("固件 %d 字节, %d 个压缩段" % (len(raw), raw.count(b"_FVH")))

    probe = guid_bytes(PROBE_GUID)
    for idx, dec in enumerate(walk_lzma_sections(raw), 1):
        p = dec.find(probe)
        if p < 0:
            continue
        ftype = dec[p + 18]
        fsize = dec[p + 20] | (dec[p + 21] << 8) | (dec[p + 22] << 16)
        print("探针在压缩段 #%d 里: type=0x%02x (0x07=DXE驱动) size=%d" % (idx, ftype, fsize))
        found_any = False
        for name, text in MARKERS.items():
            hit = text.encode("utf-16-le") in dec
            print("  %-24s %s" % (name, "YES" if hit else "-"))
            found_any = found_any or hit
        if not found_any:
            print("  (没匹配到已知版本的标记字符串)")
        return 0

    print("探针 GUID 未找到（这份固件里没有探针）")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
