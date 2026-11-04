#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Build build/fuxi-touch/libFuxiTouch.a for the fuxi kernel.

The archive holds the board probe (kits/fuxi/FuxiTouchProbe.cpp) with the HID glue it starts (kits/fuxi/FuxiHidProbe.cpp),
the FTM5 protocol and contact tracking (FuxiFtsTouch),
the GENI SPI engine (QcomGeniSpi) and the RPMh request helpers (kits/fuxi/QcomRpmh.c). They are compiled with the flags of
the XNU build's own compile records, as UniXNU-sheng builds its probes: the C++ probe from the record of iokit
IOPlatformExpert.cpp, the C sources from the record of osfmk startup.c, with XNU's warning flags replaced by
-Wall -Wextra -Werror and the same few exceptions. bsd_init calls native_touch_probe() (patches/xnu/fuxi-touch-probe.patch),
and fuxi_defconfig passes the archive to the link in CONFIG_XNU_EXTRA_LD_ARCHIVES.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]   # the assembled build tree: scripts are copied into it
OUT = ROOT / 'build/fuxi-touch'
OBJ = ROOT / 'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837'
KIT = ROOT / 'kits/fuxi'
CXX_FLAGS = ['-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-Wno-unnecessary-virtual-specifier',
             '-Wno-c99-designator', '-Wno-reorder-init-list', '-Wno-deprecated-enum-enum-conversion']
C_FLAGS = ['-Wall', '-Wextra', '-Werror', '-mgeneral-regs-only']


def record(path):
    if not path.is_file():
        sys.exit(f'{path} missing: the XNU pass of the kernel step has not left its compile records')
    return json.loads(path.read_text().strip().rstrip(','))


def command(rec, source, obj, extra):
    """The record's command for another source and object, without XNU's warning flags and dependency outputs."""
    args, out, i = rec['arguments'], [], 0
    while i < len(args):
        arg = args[i]
        if arg == rec['file']:
            out.append(str(source))
        elif arg in ('-o', '-MF', '-MT', '-MJ'):
            if arg == '-o':
                out += ['-o', str(obj)]
            i += 1
        elif arg == '-Xclang' and i + 1 < len(args) and args[i + 1].startswith('-W'):
            i += 1
        elif not arg.startswith('-W'):
            out.append(arg)
        i += 1
    return out + [str(x) for x in extra]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cxx = record(OBJ / 'iokit/DEVELOPMENT/IOPlatformExpert.cpo.json')
    c = record(OBJ / 'osfmk/DEVELOPMENT/startup.o.json')
    osfmk = ['-I', ROOT / '.cache/xnu-work/osfmk']
    includes = ['-I', KIT, '-I', ROOT / 'drivers/FuxiFtsTouch', '-I', ROOT / 'drivers/QcomGeniSpi']
    jobs = [(cxx, KIT / 'FuxiTouchProbe.cpp', CXX_FLAGS + osfmk + includes),
            (cxx, KIT / 'FuxiHidProbe.cpp', CXX_FLAGS + osfmk + includes)]
    for source in (ROOT / 'drivers/FuxiFtsTouch/FtsProtocol.c', ROOT / 'drivers/FuxiFtsTouch/FtsTouchCore.c',
                   ROOT / 'drivers/QcomGeniSpi/GeniSpi.c', KIT / 'QcomRpmh.c'):
        jobs.append((c, source, C_FLAGS + osfmk))
    objects = []
    for rec, source, flags in jobs:
        if not source.is_file():
            sys.exit(f'{source} missing: select FuxiFtsTouch and QcomGeniSpi in board.toml [components]')
        obj = OUT / (source.stem + '.o')
        subprocess.run(command(rec, source, obj, flags), cwd=rec['directory'], check=True, timeout=180)
        objects.append(obj)
        print(f'compiled {source.relative_to(ROOT)}')
    archive = OUT / 'libFuxiTouch.a'
    archive.unlink(missing_ok=True)
    ar = ['xcrun', 'ar'] if shutil.which('xcrun') else [shutil.which('llvm-ar') or 'ar']
    subprocess.run([*ar, 'rcs', str(archive), *map(str, objects)], check=True, timeout=60)
    print(f'touch archive: {archive.relative_to(ROOT)} ({len(objects)} objects)')


if __name__ == '__main__':
    main()
