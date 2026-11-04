#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Check the HID bindings of the fuxi kernel after the link: ShengHidInput's NativeHidInput against the original IOHIDFamily.

usage: check-hid-bindings.py <prelinked kernel.macho> [--contract-only]

scripts/build-fuxi-hid-input.py builds NativeHidInput (kits/fuxi/NativeHidInput.cpp, an unchanged copy of UniXNU
ShengHidInput 71a40e7) without a prelinked reference: its IOHIDDevice imports are bound to the kernelcache addresses in
scripts/fuxi_hid_abi.py. This script checks those addresses in the kernel that ships:

- the original IOHIDFamily: the instructions UniXNU's build-sheng-hid-input.py pins, getMetaClass returning the bound
  metaclass, and IOHIDDevice's 207-slot vtable, whose own slots must hold the bound addresses and whose other slots
  IOService's methods; the prelinker must have bound the family to this kernel's IOService constructor and destructor;
- unless --contract-only: the symbols the touch probe needs, the absolute bindings, and NativeHidInput's vtable, every slot
  of which is either one of its own ten or the entry of the original table.
It reads the Mach-O itself, so it runs without Xcode.
"""
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from fuxi_hid_abi import BINDINGS, CODE, KEXT_SLOTS, OVERRIDES, OWNED, SLOTS, VPTR

NEEDED = ['_native_hid_touch_allocate', '__GLOBAL__sub_I_NativeHidInput.cpp', '_fuxi_hid_start', '_native_hid_live_checkpoint',
          '_native_hid_input_observed', '_native_hid_input_requested', '__ZTV14NativeHidInput']


def fail(message):
    raise SystemExit('check-hid-bindings: ' + message)


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    contract_only = '--contract-only' in sys.argv[2:]
    data = open(sys.argv[1], 'rb').read()
    if struct.unpack_from('<I', data)[0] != 0xfeedfacf:
        fail('not a 64-bit Mach-O')
    segments, symtab, at = [], None, 32
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        cmd, size = struct.unpack_from('<II', data, at)
        if cmd == 0x19:
            segments.append((data[at + 8:at + 24].rstrip(b'\0').decode(), *struct.unpack_from('<QQQQ', data, at + 24)))
        elif cmd == 2:
            symtab = struct.unpack_from('<IIII', data, at + 8)
        at += size
    if symtab is None:
        fail('no symbol table')

    def segment(va):
        return next((name for name, vm, size, _, _ in segments if vm <= va < vm + size), None)

    def read(va, n):
        for _, vm, _, fileoff, filesize in segments:
            if vm <= va and va + n <= vm + filesize:
                return data[fileoff + va - vm:fileoff + va - vm + n]
        fail(f'{va:#x} is not backed by the file')

    def words(va, n):
        return struct.unpack(f'<{n}Q', read(va, 8 * n))

    symoff, nsyms, stroff, _ = symtab
    names = {}
    for i in range(nsyms):
        strx, kind, _, _, value = struct.unpack_from('<IBBHQ', data, symoff + 16 * i)
        if not kind & 0xe0 and kind & 0x0e:
            names[data[stroff + strx:data.index(b'\0', stroff + strx)].decode()] = value

    for va, want in CODE.items():
        if read(va, len(want) // 2).hex() != want:
            fail(f'IOHIDFamily instructions at {va:#x} differ from the pinned contract')
    # getMetaClass (slot 7) is adrp x0 / add x0 / ret: the metaclass it returns is the one bound as gMetaClass.
    adrp, add = struct.unpack('<2I', read(KEXT_SLOTS[7], 8))
    if adrp & 0x9f00001f != 0x90000000 or add & 0xffc003ff != 0x91000000:
        fail('IOHIDDevice::getMetaClass is not adrp/add x0')
    page = ((adrp >> 29 & 3) | (adrp >> 5 & 0x7ffff) << 2) << 12
    page -= 1 << 33 if page & 1 << 32 else 0
    meta = (KEXT_SLOTS[7] & ~0xfff) + page + (add >> 10 & 0xfff)
    if meta != BINDINGS['__ZN11IOHIDDevice10gMetaClassE']:
        fail(f'IOHIDDevice::getMetaClass returns {meta:#x}, not the bound gMetaClass')
    original = words(VPTR, SLOTS)
    service = words(names['__ZTV9IOService'] + 16, 168)
    if read(VPTR + SLOTS * 8, 24) != bytes(24):
        fail('IOHIDDevice vtable is not 207 slots')
    if [i for i in range(168) if original[i] != service[i]] != OVERRIDES:
        fail('IOHIDDevice overrides other IOService slots than the pinned ones')
    if [i for i, a in enumerate(original) if a == names['___cxa_pure_virtual']] != [180]:
        fail('IOHIDDevice pure slots changed')
    for slot, va in KEXT_SLOTS.items():
        if original[slot] != va or segment(va) != '__PLK_TEXT_EXEC':
            fail(f'IOHIDDevice slot {slot} holds {original[slot]:#x}, not {va:#x}')
    # The family's constructor and destructor call IOService's through bindings the prelinker filled in.
    if words(0xfffffff005d00f10, 2) != (names['__ZN9IOServiceC2EPK11OSMetaClass'], names['__ZN9IOServiceD2Ev']):
        fail('IOHIDFamily is not bound to this kernel\'s IOService constructor and destructor')
    print('IOHIDFamily contract: instructions, metaclass, 207-slot vtable and IOService bindings as pinned')
    if contract_only:
        return
    missing = [name for name in NEEDED if name not in names]
    if missing:
        fail('missing from the kernel: ' + ', '.join(missing))
    for name, va in BINDINGS.items():
        if names.get(name) != va:
            fail(f'{name} is bound to {names.get(name, 0):#x}, not {va:#x}')
    own = words(names['__ZTV14NativeHidInput'] + 16, SLOTS)
    owned = [slot for slot in range(SLOTS) if own[slot] != original[slot]]
    if owned != OWNED:
        fail(f'NativeHidInput differs from the original table in slots {owned}, not only in its own {OWNED}')
    outside = [slot for slot in owned if segment(own[slot]) != '__TEXT_EXEC']
    if outside:
        fail(f'NativeHidInput slots {outside} point outside the kernel text')
    print(f'NativeHidInput: {len(OWNED)} own slots, {SLOTS - len(OWNED)} as in the original table; {len(NEEDED)} symbols defined')


if __name__ == '__main__':
    main()
