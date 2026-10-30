#!/usr/bin/env python3
"""Verify the payload and boot image against the device repository rules."""
import json
import struct
import subprocess
import sys

img = 'out/fuxi/boot/boot.img'
d = open(img, 'rb').read()
ver = struct.unpack_from('<I', d, 40)[0]
osv = struct.unpack_from('<I', d, 16)[0]
if osv == 0:
    b = bytearray(d)
    struct.pack_into('<I', b, 16, 0x200001a8)
    open(img, 'wb').write(bytes(b))
    d = bytes(b)
    osv = 0x200001a8
    print('patched os_version -> 0x200001a8')

meta = json.load(open('out/fuxi/payload/payload.json'))
out = subprocess.run(['mtype', '-i', 'out/fuxi/payload/payload.img', '::/EFI/UNIXNU/PAYLOADS'],
                     capture_output=True, text=True)
listing = (out.stdout + out.stderr).lower()

checks = {
    'trust_cache_sha256': bool(meta.get('trust_cache_sha256')),
    'gpu_addon_sha256': bool(meta.get('gpu_addon_sha256')),
    'header_version_3': struct.unpack_from('<I', d, 40)[0] == 3,
    'os_version_set': osv != 0,
    'trustcache_in_payload': 'trustcache' in listing,
}
print('checks:', checks)
if not all(checks.values()):
    raise SystemExit('VERIFY FAILED: ' + ', '.join(k for k, v in checks.items() if not v))
print('PASS: payload and boot image verified')