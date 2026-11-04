#!/usr/bin/env python3
"""把 XNU 内核装进 UEFI 的 payload FAT，打成 boot.img 并（可选）刷入。

背景：UFS 走不通（SmemDxe 在 0x81D00000 读到全零、断言后死循环），所以内核
不放在存储上，而是塞进 FD 里的 FAT16 镜像，由 FuxiRamDiskDxe 发布成 BlockIo，
DiskIoDxe/PartitionDxe/FatDxe 自动叠上去，DarwinBoot 就能用
SimpleFileSystem 打开 \\kernel 和 \\kernel.adt。

布局（和 MemoryMapLib、fuxi.toml 必须一致）：

    payload = BootShim(192) + FV(0x300000) + FAT(0x1100000)
    FD_BASE = 0xC0000000, FD_SIZE = 0x1400000
    FAT 落在 0xC0300000

用法：
    mkpayload.py --kernel K --adt A [--toml T] [--uefi-src DIR] [--out DIR]
                 [--no-flash]

默认从 E:\\download\\uefi-sheng 取 BootShim.bin / FV / mkbootimg.py，
从 E:\\ios-on-fuxi 取 mkfat.py 和 unixnu.toml。
"""

import argparse
import gzip
import io
import os
import struct
import subprocess
import sys

UEFI_SRC = r"E:\download\uefi-sheng"
REPO = r"E:\ios-on-fuxi"
OUT = r"E:\download\uefi-build"
DTB = r"C:\Users\徐智伟\Doubao\chats\2026-10-20\new-chat\fuxi-real.dtb"
FASTBOOT = os.path.join(REPO, r"scripts\adb-platform-tools-latest-windows\platform-tools\fastboot.exe")

FD_SIZE = 0x1400000
FV_SIZE = 0x300000
FAT_SIZE = 0x1100000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kernel", required=True)
    ap.add_argument("--adt", required=True)
    ap.add_argument("--toml", default=os.path.join(REPO, "tools", "unixnu.toml"))
    ap.add_argument("--uefi-src", default=UEFI_SRC)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--no-flash", action="store_true")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)

    ksize = os.path.getsize(a.kernel)
    asize = os.path.getsize(a.adt)
    print("kernel %d 字节, adt %d 字节" % (ksize, asize))
    if ksize + asize > FAT_SIZE - 0x20000:
        sys.exit("内核太大，FAT 装不下（上限约 16.9 MB）")

    payload = os.path.join(a.out, "payload.img")
    rc = subprocess.call([
        sys.executable, os.path.join(REPO, "tools", "mkfat.py"),
        payload, "17",
        "kernel=%s" % a.kernel,
        "kernel.adt=%s" % a.adt,
        "EFI/UniXNU/unixnu.toml=%s" % a.toml,
    ])
    if rc != 0:
        sys.exit("mkfat 失败")
    assert os.path.getsize(payload) == FAT_SIZE, hex(os.path.getsize(payload))

    shim = open(os.path.join(a.uefi_src, "BootShim", "BootShim.bin"), "rb").read()
    fv = open(os.path.join(a.uefi_src, "Build", "fuxiPkg", "DEBUG_CLANGPDB", "FV", "SILICIUM_UEFI.fd"), "rb").read()
    if len(fv) != FV_SIZE:
        sys.exit("FV 不是 %d 字节而是 %d，先重新编译 UEFI" % (FV_SIZE, len(fv)))
    fat = open(payload, "rb").read()
    dtb = open(DTB, "rb").read()

    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as g:
        g.write(shim + fv + fat)
    gz = buf.getvalue()
    kern = os.path.join(a.out, "Image-payload.gz-dtb")
    open(kern, "wb").write(gz + dtb)
    print("gzip %d + dtb %d" % (len(gz), len(dtb)))

    empty = os.path.join(a.out, "empty-ramdisk")
    open(empty, "wb").close()
    boot = os.path.join(a.out, "boot-uefi-xnu.img")
    rc = subprocess.call([
        sys.executable, os.path.join(a.uefi_src, "Resources", "Scripts", "mkbootimg.py"),
        "--kernel", kern, "--ramdisk", empty,
        "--base", "0x00000000", "--kernel_offset", "0x00008000",
        "--tags_offset", "0x01e00000", "--pagesize", "4096",
        "--header_version", "0", "--os_version", "13.0.0",
        "--os_patch_level", "2022-11", "-o", boot,
    ])
    if rc != 0:
        sys.exit("mkbootimg 失败")

    d = open(boot, "rb").read()
    print("boot.img %d 字节, kernel_size %d, os_version 0x%08X"
          % (len(d), struct.unpack_from("<I", d, 8)[0], struct.unpack_from("<I", d, 0x2C)[0]))

    if a.no_flash:
        return
    for part in ("boot_a", "boot_b"):
        subprocess.call([FASTBOOT, "flash", part, boot])
    subprocess.call([FASTBOOT, "reboot"])


if __name__ == "__main__":
    sys.exit(main())