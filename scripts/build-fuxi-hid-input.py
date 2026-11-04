#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Build build/sheng-hid-input/libShengHidInput.a: UniXNU ShengHidInput's touch digitizer for fuxi.

NativeHidInput (kits/fuxi/NativeHidInput.cpp, an unchanged copy of UniXNU ShengHidInput 71a40e7 NativeHidInput.cpp)
derives from the original IOHIDDevice of IOHIDFamily-2031.120.4 in the iPadOS 17.7.11 kernelcache. kits/fuxi/FuxiHidProbe.cpp
loads the family, registers NativeHidInput's metaclass and starts the touch-only device once sensing runs (fuxi-touch-hid=1).

This script is UniXNU scripts/build-sheng-hid-input.py (6ae4c25) with two changes:
- it reads no prelinked reference candidate. UniXNU's reads one left by an earlier sheng build, which a fresh CI tree does
  not have. IOHIDDevice's own methods are bound to their kernelcache addresses (scripts/fuxi_hid_abi.py), and
  ci/check-hid-bindings.py checks them, the pinned IOHIDFamily instructions and the original vtable in the kernel that ships;
- it compiles the source itself with the flags of build-arm-driver.py (the compile record of IOPlatformExpert.cpp), as
  scripts/build-fuxi-platform-power.py does, since build-arm-driver.py looks for the source in drivers/ShengHidInput.
Every check that needs only the compiled object is kept. fuxi_defconfig force-loads the archive.
"""
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]   # the assembled build tree: scripts are copied into it
OUT = ROOT / 'build/sheng-hid-input'
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / 'kits/XnuPrelink'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_prelink import macho
from fuxi_hid_abi import BINDINGS, KEXT_SLOTS, OWNED, SLOTS


def run(command, **kwargs):
    return subprocess.check_output([str(v) for v in command], timeout=90, **kwargs)


def require(value, message):
    if not value:
        raise SystemExit(message)


# The original device as UniXNU's builder declares it: opaque storage, the IOService methods IOHIDDevice overrides, and its
# own slots 168 to 206, of which NativeHidInput may implement only the four declared with a prototype.
header = '''// Generated from the qualified original image; opaque private storage only.
#pragma once
#include <IOKit/IOService.h>
#include <IOKit/IOMemoryDescriptor.h>
class IOHIDDevice : public IOService {
 OSDeclareAbstractStructors(IOHIDDevice)
 unsigned char originalPrivate[0xd0-sizeof(IOService)];
public:
 using IOService::setProperty;
 IOReturn Dispatch(IORPC) override;
 void free() override;
 bool init(OSDictionary *properties=nullptr) override;
 bool setProperty(const OSSymbol *,OSObject *) override;
 bool willTerminate(IOService *,IOOptionBits) override;
 IOReturn configureReport(IOReportChannelList *,IOReportConfigureAction,void *,void *) override;
 IOReturn updateReport(IOReportChannelList *,IOReportUpdateAction,void *,void *) override;
 bool start(IOService *) override;
 void stop(IOService *) override;
 bool handleOpen(IOService *,IOOptionBits,void *) override;
 void handleClose(IOService *,IOOptionBits) override;
 bool handleIsOpen(const IOService *) const override;
 bool matchPropertyTable(OSDictionary *,SInt32 *) override;
 IOReturn message(UInt32,IOService *,void *) override;
 IOReturn newUserClient(task_t,void *,UInt32,OSDictionary *,IOUserClient **) override;
'''
for i in range(168, SLOTS):
    if i == 171:
        header += ' virtual OSString *newTransportString() const;\n'
    elif i == 173:
        header += ' virtual OSString *newProductString() const;\n'
    elif i == 180:
        header += ' virtual IOReturn newReportDescriptor(IOMemoryDescriptor **) const=0;\n'
    elif i == 181:
        header += ' virtual IOReturn handleReport(IOMemoryDescriptor *,unsigned,IOOptionBits);\n'
    else:
        header += f' virtual __attribute__((deprecated("Unqualified prototype: never call from source"))) void opaque{i}();\n'
header += '};\nstatic_assert(sizeof(IOHIDDevice)==0xd0,"Original device instance size");\n'
(OUT / 'OriginalHidDeviceABI.h').write_text(header)

source = ROOT / 'kits/fuxi/NativeHidInput.cpp'
obj = OUT / 'NativeHidInput.o'
record = json.loads((ROOT / 'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/IOPlatformExpert.cpo.json').read_text().strip().rstrip(','))
command, i = [], 0
arguments = record['arguments']
while i < len(arguments):
    arg = arguments[i]
    if arg == record['file']:
        command.append(source)
    elif arg == '-o':
        command += ['-o', obj]
        i += 1
    elif arg == '-Xclang' and arguments[i + 1].startswith('-W'):
        i += 1
    elif not arg.startswith('-W'):
        command.append(arg)
    i += 1
command += ['-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-Wno-c99-designator',
            '-Wno-reorder-init-list', '-Wno-deprecated-enum-enum-conversion',
            '-Wno-unnecessary-virtual-specifier', '-I', ROOT / '.cache/xnu-work/osfmk', '-I', OUT]
run(command, cwd=record['directory'])
raw = obj.read_bytes()
info = macho(raw)
require(info['kind'] == 1, 'Require actual ARM64 subtype-0 Mach-O object')
build_version = [struct.unpack_from('<2I', raw, at + 8) for cmd, at, _ in info['commands'] if cmd == 0x32]
require(build_version == [(2, 0x110000)], 'Require iOS17 build target')
sym_at = next(at for cmd, at, _ in info['commands'] if cmd == 2)
at, count, strings, _ = struct.unpack_from('<4I', raw, sym_at + 8)
symbols = []
for i in range(count):
    ix, kind, _, _, address = struct.unpack_from('<IBBHQ', raw, at + i * 16)
    symbols.append((raw[strings + ix:raw.index(b'\0', strings + ix)].decode(), address, kind))
vtable = next(va for name, va, _ in symbols if name == '__ZTV14NativeHidInput')
relocations = {}
for segment in info['segments']:
    for section in segment['sections']:
        if section['va'] <= vtable < section['va'] + section['size']:
            at, count = struct.unpack_from('<2I', raw, section['command_offset'] + 56)
            for i in range(count):
                offset, bits = struct.unpack_from('<2I', raw, at + i * 8)
                if bits >> 27 & 1 and bits >> 28 == 0 and bits >> 25 & 3 == 3:
                    relocations[section['va'] + offset] = symbols[bits & 0xffffff][0]
entries = [relocations.get(vtable + 16 + i * 8) for i in range(SLOTS)]
require(all(entries) and vtable + 16 + SLOTS * 8 not in relocations, 'Compiled exact 207-slot vtable')
bindings = dict(BINDINGS)
owned = []
for slot, name in enumerate(entries):
    if name.startswith(('__ZN14NativeHidInput', '__ZNK14NativeHidInput')):
        owned.append(slot)
    elif '11IOHIDDevice' in name:
        require(slot in KEXT_SLOTS, f'IOHIDDevice method at slot {slot} has no kernelcache address')
        require(bindings.get(name, KEXT_SLOTS[slot]) == KEXT_SLOTS[slot], f'One address for {name}')
        bindings[name] = KEXT_SLOTS[slot]
    else:
        # Inherited from IOService: ci/check-hid-bindings.py compares the linked table with the original one.
        require(slot < 168 and slot not in KEXT_SLOTS, f'IOService method expected at slot {slot}')
require(owned == OWNED, 'Only qualified HID methods overridden')
undefined = {n for n, _, k in symbols if k == 1 and '11IOHIDDevice' in n}
require(undefined == set(bindings), 'All and only actual original HID imports bound')
asm = OUT / 'original-bindings.S'
asm.write_text(''.join(f'.globl {name}\n.set {name}, {va:#x}\n' for name, va in sorted(bindings.items())))
sdk = run(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
run(['xcrun', 'clang', '-target', 'arm64-apple-ios17.0', '-isysroot', sdk, '-c', asm, '-o', OUT / 'hid-original-bindings.o'])
late = OUT / 'NativeHidInput.late.o'
objcopy = shutil.which('llvm-objcopy') or '/opt/homebrew/opt/llvm/bin/llvm-objcopy'
run([objcopy, '--remove-section=__DATA,__mod_init_func', '--globalize-symbol=__GLOBAL__sub_I_NativeHidInput.cpp', obj, late])


def text_section(blob):
    section = next(s for seg in macho(blob)['segments'] for s in seg['sections'] if s['name'] == '__text')
    return blob[section['fileoff']:section['fileoff'] + section['size']]


require(text_section(raw) == text_section(late.read_bytes()), 'Owned code unchanged by deferred metaclass registration')
archive = OUT / 'libShengHidInput.a'
archive.unlink(missing_ok=True)
run(['xcrun', 'ar', 'rcs', archive, late, OUT / 'hid-original-bindings.o'])
report = {'source': str(source.relative_to(ROOT)), 'original_slots': SLOTS, 'original_instance_size': 0xd0,
          'owned_slots': owned, 'bindings': {name: hex(va) for name, va in sorted(bindings.items())}}
(OUT / 'build-report.json').write_text(json.dumps(report, indent=2) + '\n')
print(f'PASS: NativeHidInput {len(owned)} own slots, {len(bindings)} original imports bound; archive {archive.relative_to(ROOT)}')
