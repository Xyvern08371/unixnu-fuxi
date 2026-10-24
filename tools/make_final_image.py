#!/usr/bin/env python3
"""合成最终 boot.img：shim（带 UFS 探测）+ 新内核 payload + DTB。

shim 的 payload 偏移会随代码大小变化，所以这里自动搜索 payload 魔数并校验头部。
"""

import gzip
import io
import struct
import subprocess
import sys

KERNEL = r"E:\download\xnu-kernel-20\out\kernel.development.fuxi"
import os as _os
SHIM_IMG = _os.environ.get("SHIM_IMG", r"E:\download\shim13-img.bin")
ADT = r"E:\ios-on-fuxi\rom\xnu\fuxi.adt"
DTB = r"E:\ios-on-fuxi\rom\device\fuxi_runtime.dtb"
OUT_IMG = r"E:\download\boot-shim-final.img"
OUT_PAYLOAD = r"E:\download\payload-final.bin"


def find_payload_off(img: bytes) -> int:
    """找到 payload 起点：魔数 FUXIXNU，且后面 0x10 处的 virt_base/entry 合理"""
    magic = b"FUXIXNU\x00"
    start = 0
    while True:
        i = img.find(magic, start)
        if i < 0:
            raise SystemExit("找不到 payload 魔数")
        start = i + 1
        if i + 0x60 > len(img):
            continue
        nseg, = struct.unpack_from("<I", img, i + 12)
        virt, entry, adt_off = struct.unpack_from("<3Q", img, i + 0x10)
        if 1 <= nseg <= 32 and virt > 0xFFFF000000000000 and entry > virt and adt_off < len(img):
            return i


def main() -> int:
    # 1) 找 payload 偏移
    img = bytearray(io.open(SHIM_IMG, "rb").read())
    off = find_payload_off(bytes(img))
    print(f"shim Image {len(img):,} 字节，payload 位于 0x{off:x}")

    # 2) 生成 payload（若已提供则直接用）
    import os as _os
    if _os.environ.get("USE_PAYLOAD"):
        payload = io.open(_os.environ["USE_PAYLOAD"], "rb").read()
        print(f"  使用现成 payload: {_os.environ['USE_PAYLOAD']} ({len(payload):,} 字节)")
        r = None
    else:
        r = subprocess.run(
        [sys.executable, r"E:\ios-on-fuxi\tools\mkpayload_fuxi.py",
         KERNEL, ADT, OUT_PAYLOAD,
         "--cmdline", "debug=0xc serial=3 cpus=1 keepsyms=1 -v"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=r"E:\ios-on-fuxi")
    if r is not None:
        for line in (r.stdout or "").split("\n"):
            if line.strip():
                print("  " + line.strip())
        if r.returncode != 0:
            print(r.stderr[-800:])
            return 1
        payload = io.open(OUT_PAYLOAD, "rb").read()

    # 3) 替换 payload 并修正 image_size
    out = bytearray(img[:off]) + payload
    struct.pack_into("<Q", out, 0x10, len(out))
    io.open(r"E:\download\shim-final-img.bin", "wb").write(bytes(out))
    print(f"新 Image: {len(out):,} 字节")

    # 4) gzip + 打包（含 DTB）
    gz_path = r"E:\download\shim-final.gz"
    io.open(gz_path, "wb").write(gzip.compress(bytes(out), 9, mtime=0))
    r = subprocess.run(
        [sys.executable, r"E:\ios-on-fuxi\tools\mkshim_bootimg.py",
         "--kernel", gz_path, "--dtb", DTB, "--output", OUT_IMG],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=r"E:\ios-on-fuxi")
    for line in (r.stdout or "").split("\n"):
        if line.strip():
            print("  " + line.strip())
    if r.returncode != 0:
        print(r.stderr[-800:])
        return 1

    print(f"\n✅ 可刷镜像: {OUT_IMG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
