#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Build build/sheng-ufs/libShengUfs.a from the fuxi NativeUfs driver.

The kernel link (scripts/build-xnu-4k-baseline.sh) force-loads
build/sheng-ufs/libShengUfs.a when CONFIG_XNU_NATIVE_UFS=y, and that path is fixed there,
so this device-local script compiles drivers/NativeUfs/NativeUfs.cpp with the same flags
UniXNU's build-arm-driver.py applies to the NativeUfs legacy component, and emits the
archive at that fixed path. No component catalog entry is required; the runtime class and
bundle id stay NativeUfs / org.blu-sharky.NativeUfs.

NativeUfs, VerifiedRoot and VirtioMmioBlock are not selected components, so the assembled
tree does not link their directories. Resolve the device checkout and the UniXNU checkout
through already-linked symlinks and reference those sources/headers by absolute path.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]   # the assembled build tree: scripts are copied into it
OUT = ROOT / 'build/sheng-ufs'
OBJ = ROOT / 'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837'


def resolve_native_ufs():
    """Resolve the device checkout through the already-linked drivers/FuxiFtsTouch
    symlink and link drivers/NativeUfs into the tree when it is missing."""
    native = ROOT / 'drivers/NativeUfs'
    if (native / 'NativeUfs.cpp').is_file():
        return native
    fts = ROOT / 'drivers/FuxiFtsTouch'
    if fts.is_symlink():
        candidate = fts.resolve().parent / 'NativeUfs'
        if (candidate / 'NativeUfs.cpp').is_file():
            if not native.exists():
                native.symlink_to(candidate, target_is_directory=True)
            return native
    sys.exit(f'{native}/NativeUfs.cpp missing: add the drivers/NativeUfs submodule first')


def resolve_unixnu_root():
    """VerifiedRoot and VirtioMmioBlock are not selected components, so the tree does
    not link their directories. Resolve the UniXNU checkout root through an
    already-linked UniXNU directory and reference those headers by absolute path."""
    for link in ('kits/XnuPrelink', 'drivers/ArmCpu', 'drivers/ArmDTPlatform', 'drivers/SoftwareAES'):
        path = ROOT / link
        if path.is_symlink():
            return path.resolve().parents[1]
    sys.exit('cannot resolve the UniXNU checkout root from the assembled tree')


SOURCE = resolve_native_ufs() / 'NativeUfs.cpp'

CXX_FLAGS = ['-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
             '-Wno-c99-designator', '-Wno-reorder-init-list',
             '-Wno-deprecated-enum-enum-conversion', '-Wno-unnecessary-virtual-specifier']


def ufs_extra(unixnu):
    # Stage 2 (APFS root mount): enable verified-block so NativeUfs verifies each
    # read against the signed root policy (vr_* / verified_root_* symbols from
    # libVerifiedRootProbe.a). The includes/defines match build-arm-driver.py's
    # NativeUfs legacy component.
    return ['-I', ROOT / '.cache/xnu-work/osfmk',
            '-I', ROOT / 'build/storage-abi/include',
            '-I', unixnu / 'kits/VerifiedRoot/include',
            '-I', unixnu / 'drivers/VirtioMmioBlock',
            '-DNATIVE_VERIFIED_BLOCK=1',
            '-DNATIVE_VERIFIED_BLOCK_MULTI_POLICY=1',
            '-mgeneral-regs-only']


def record(path):
    if not path.is_file():
        sys.exit(f'{path} missing: the XNU pass of the kernel step has not left its compile records')
    return json.loads(path.read_text().strip().rstrip(','))


def command(rec, source, obj, extra):
    """The record's command for another source and object, without XNU's warning flags."""
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
    if not SOURCE.is_file():
        sys.exit(f'{SOURCE} missing: add the drivers/NativeUfs submodule first')
    unixnu = resolve_unixnu_root()
    rec = record(OBJ / 'iokit/DEVELOPMENT/IOPlatformExpert.cpo.json')
    obj = OUT / 'NativeUfs.o'
    subprocess.run(command(rec, SOURCE, obj, CXX_FLAGS + ufs_extra(unixnu)),
                   cwd=rec['directory'], check=True, timeout=180)
    print(f'compiled {SOURCE.relative_to(ROOT)}')
    archive = OUT / 'libShengUfs.a'
    archive.unlink(missing_ok=True)
    ar = ['xcrun', 'ar'] if shutil.which('xcrun') else [shutil.which('llvm-ar') or 'ar']
    subprocess.run([*ar, 'rcs', str(archive), str(obj)], check=True, timeout=60)
    print(f'UFS archive: {archive.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
