#!/usr/bin/env python3
"""Force XNU_BOOT_PROGRESS=1 in the boot-progress archive build.

The archive compiles from compile records left by the bootstrap pass, which
runs with XNU_BOOT_PROGRESS=0 (written as the two tokens '-D' and
'XNU_BOOT_PROGRESS=0'). BootProgress.c then sees the header stub macro and
fails to compile itself, and passing a second define trips -Wmacro-redefined.
"""
import io
import pathlib
import sys

OLD = """        elif not value.startswith('-W'):
            command.append(value)"""
NEW = """        elif value == '-D' and index + 1 < len(arguments) and arguments[index + 1].startswith('XNU_BOOT_PROGRESS='):
            index += 1
        elif not value.startswith('-W') and not value.startswith('XNU_BOOT_PROGRESS='):
            command.append(value)"""

OLD_TAIL = "    command += extra"
NEW_TAIL = ("    command = [a for a in command if not a.startswith('-DXNU_BOOT_PROGRESS=')]\n"
            "    command += ['-DXNU_BOOT_PROGRESS=1']  # XNU_BOOT_PROGRESS=1 forced\n"
            "    command += extra")

targets = [pathlib.Path('device/scripts/build-boot-progress.py'),
           pathlib.Path('out/fuxi/tree/scripts/build-boot-progress.py')]
patched = []
for p in targets:
    if not p.is_file():
        continue
    s = io.open(p, encoding='utf-8').read()
    if 'XNU_BOOT_PROGRESS=1 forced' in s:
        continue
    if OLD not in s:
        print('pattern not found in', p)
        continue
    s = s.replace(OLD, NEW, 1)
    s = s.replace(OLD_TAIL, NEW_TAIL, 1)
    io.open(p, 'w', encoding='utf-8').write(s)
    patched.append(str(p))
print('boot-progress patched:', patched)