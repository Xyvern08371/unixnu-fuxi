#!/usr/bin/env python3
"""Force XNU_BOOT_PROGRESS=1 in the boot-progress archive build.

The archive compiles from compile records left by the bootstrap pass, which
runs with XNU_BOOT_PROGRESS=0; BootProgress.c then sees the header's stub
macro and fails to compile itself.
"""
import io
import pathlib
import re
import sys

targets = [pathlib.Path('device/scripts/build-boot-progress.py'),
           pathlib.Path('out/fuxi/tree/scripts/build-boot-progress.py')]
patched = []
for p in targets:
    if not p.is_file():
        continue
    s = io.open(p, encoding='utf-8').read()
    if 'XNU_BOOT_PROGRESS=1 forced' in s:
        continue
    # drop any recorded value and pin the define
    s = re.sub(r"'-DXNU_BOOT_PROGRESS=[0-9]+',\s*", "", s)
    s = s.replace("command += extra",
                  "command = [a for a in command if not a.startswith('-DXNU_BOOT_PROGRESS=')]\n"
                  "    command += ['-DXNU_BOOT_PROGRESS=1']  # XNU_BOOT_PROGRESS=1 forced\n"
                  "    command += extra", 1)
    io.open(p, 'w', encoding='utf-8').write(s)
    patched.append(str(p))
print('boot-progress patched:', patched)