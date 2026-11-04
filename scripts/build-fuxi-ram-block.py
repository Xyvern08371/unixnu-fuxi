#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Publish the fuxi RamBlock storage bindings for the kernel link.

The fork's build-arm-driver.py compiles NativeRamBlock.o + libRamBlock.a but
does not emit bindings.json. The kernel baseline, when both NATIVE_RAM_BLOCK
and NATIVE_VIRTIO_BLOCK are on, reads bindings.json next to each transport
archive and compares their original IOBlockStorageDevice imports. fuxi has no
live interface-audit.json, so it reuses the same pinned addresses as the
Virtio transport (scripts/data/native-storage-original-bindings.S).

This script also exposes the component object under the archive-derived name
the baseline derives (libRamBlock.a -> RamBlock.o)."""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/ram-block'


def main():
    object_src = OUT / 'NativeRamBlock.o'
    if not object_src.is_file():
        # component:RamBlock builds the object; it must run first.
        sys.exit(f'{object_src} missing: keep component:RamBlock before this script in [kernel].archives')

    source = ROOT / 'scripts/data/native-storage-original-bindings.S'
    text = source.read_text()
    bindings = {}
    for line in text.splitlines():
        match = re.match(r'\.set\s+(\S+),\s*(0x[0-9a-fA-F]+)', line)
        if match:
            bindings[match.group(1)] = match.group(2)
    if not bindings:
        sys.exit('Pinned original storage bindings are empty')

    object_link = OUT / 'RamBlock.o'
    if object_link.is_symlink() or object_link.is_file():
        object_link.unlink()
    object_link.symlink_to(object_src)

    (OUT / 'bindings.json').write_text(json.dumps(dict(
        compiled_object_sha256=hashlib.sha256(object_src.read_bytes()).hexdigest(),
        bindings=bindings, original_code_modified=False,
        live_capture=False), indent=2) + chr(10))
    print(f'fuxi ram-block bindings: {len(bindings)} storage bindings')


if __name__ == '__main__':
    main()
