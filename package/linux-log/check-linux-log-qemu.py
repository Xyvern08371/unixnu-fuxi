#!/usr/bin/env python3
"""Offline check of the log reader path: QEMU virt boots the reader's kernel and initramfs (taken from the built image) with a virtio disk
whose GPT holds a "userdata" partition; its last 32 MiB carry a synthetic log window in BootLog.c's layout. scripts/read-sheng-log.py then
fetches the window over the QEMU serial port (a pty standing in for the USB ACM shell) and the decoded slots and message buffer must match.
This proves partition lookup, the copy, the transfer and the decoder; not USB, UFS or the XNU writer.

usage: check-linux-log-qemu.py --image sheng-linux-log.img --kernel Image --work DIR"""
import argparse
import os
import re
import struct
import subprocess
import sys
import time
import uuid
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if not (ROOT / 'scripts/read-sheng-log.py').is_file():
    ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
reader = __import__('read-sheng-log')

SECTOR, BLOCK = 512, 4096


def gpt_disk(path, part_sectors):
    first = 2048
    total = first + part_sectors + 2048
    entries = bytearray(128 * 128)
    name = 'userdata'.encode('utf-16-le')
    entries[0:128] = (uuid.UUID('ebd0a0a2-b9e5-4433-87c0-68b6b72699c7').bytes_le + uuid.uuid4().bytes_le +
                      struct.pack('<QQQ', first, first + part_sectors - 1, 0) + name + b'\0' * (72 - len(name)))
    ecrc = zlib.crc32(entries)

    def header(current, backup, entries_lba):
        h = bytearray(struct.pack('<8sIIIIQQQQ16sQIII', b'EFI PART', 0x10000, 92, 0, 0, current, backup, 34, total - 34,
                                  uuid.uuid4().bytes_le, entries_lba, 128, 128, ecrc))
        struct.pack_into('<I', h, 16, zlib.crc32(h))
        return bytes(h) + b'\0' * (SECTOR - 92)
    mbr = bytearray(SECTOR)
    mbr[446:462] = struct.pack('<BBBBBBBBII', 0, 0, 2, 0, 0xee, 0xff, 0xff, 0xff, 1, min(total - 1, 0xffffffff))
    mbr[510:512] = b'\x55\xaa'
    with open(path, 'wb') as f:
        f.truncate(total * SECTOR)
        f.write(mbr)
        f.write(header(1, total - 1, 2))
        f.write(entries)
        f.seek((total - 33) * SECTOR)
        f.write(entries)
        f.write(header(total - 1, 1, total - 33))
    return first


def window():
    blob = bytearray(8192 * BLOCK)
    msg = b''.join(b'kernel line %d\n' % i for i in range(3000))
    blob[1 * BLOCK:1 * BLOCK + len(msg)] = msg
    slots = []
    for n in range(5):
        text = f'#slot {n} t={2 * n}s tag=qemu-check\n[banner]\nGPUC subs={n}\n'.encode()
        at = (33 + n * 4) * BLOCK
        blob[at:at + len(text)] = text
        slots.append(text.decode())
    blob[0:120] = reader.HEADER.pack(b'SHLOG001', 1, 120, 0x1234abcd, 0x3d00000, 8192, 1, 32, len(msg), 33, 4, (8192 - 33) // 4, 5,
                                     10, 5, 0, 0, 0, 2, b'qemu-check'.ljust(32, b'\0'))
    return bytes(blob), msg, slots


def main():
    ap = argparse.ArgumentParser()
    for name in ('image', 'kernel', 'work'):
        ap.add_argument('--' + name, required=True, type=Path)
    a = ap.parse_args()
    a.work.mkdir(parents=True, exist_ok=True)
    img = a.image.read_bytes()
    kernel_size, _, ramdisk_size = struct.unpack_from('<3I', img, 8)
    page = struct.unpack_from('<I', img, 36)[0]
    at = page + (kernel_size + page - 1) // page * page
    (a.work / 'initrd.gz').write_bytes(img[at:at + ramdisk_size])
    disk = a.work / 'disk.img'
    part_sectors = 96 * 1024 * 1024 // SECTOR
    first = gpt_disk(disk, part_sectors)
    blob, msg, slots = window()
    with open(disk, 'r+b') as f:
        f.seek((first + part_sectors) * SECTOR - len(blob))
        f.write(blob)
    cmd = ['qemu-system-aarch64', '-M', 'virt', '-cpu', 'cortex-a76', '-m', '1024', '-nographic', '-monitor', 'none',
           '-serial', 'pty', '-kernel', str(a.kernel), '-initrd', str(a.work / 'initrd.gz'),
           '-append', 'rdinit=/init console=ttyAMA0 loglevel=4 logout=/dev/console logshell=/dev/ttyAMA0',
           '-drive', f'file={disk},if=none,format=raw,id=d0', '-device', 'virtio-blk-pci,drive=d0']
    q = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        pty = None
        for line in q.stdout:
            m = re.search(r'char device redirected to (/dev/\S+)', line)
            if m:
                pty = m.group(1)
                break
        if not pty:
            raise SystemExit('QEMU gave no pty')
        port = reader.Port(pty)
        port.read_until(b'ready: shell', 120)
        os.close(port.fd)
        run = reader.fetch(pty, a.work / 'out', False)
        got = (run / 'slots.txt').read_text()
        assert got == '\n'.join(slots), got[:200]
        assert (run / 'msgbuf.txt').read_bytes() == msg
        assert (run / 'latest.txt').read_text() == slots[-1]
        print('PASS: reader found userdata by GPT name in QEMU, copied the last 32 MiB, and the serial fetch decoded 5 slots and the message buffer')
    finally:
        q.kill()
        q.wait()


if __name__ == '__main__':
    main()
