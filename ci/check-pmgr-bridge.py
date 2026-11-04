#!/usr/bin/env python3
"""Check the PMGR bridge in a linked fuxi kernel: the AMFI -> PMGR contract and ShengPlatformPower's provider table.

usage: python3 ci/check-pmgr-bridge.py <prelinked kernel.macho> [--contract-only]

AMFI (com.apple.driver.AppleMobileFileIntegrity, prelinked unchanged from the iPadOS 17.7.11 kernelcache) waits for an
ApplePMGRNub service and panics with "AMFI: No PMGR?" (ConfigurationSettings.cpp:235) when none appears. With one, it
reads a value through the nub, ORs in bit 2 and writes it back; the nub dispatches both calls to the provider stored at
nub+0x88 (slots 320 and 321), and ApplePMGR's base implementations return 0xffffffff and do nothing.
package/ShengPlatformPower.cpp (UniXNU-sheng) publishes the original nub with an ApplePMGR provider whose power
operations stop with a panic. The instruction words and addresses below are the ones UniXNU's
scripts/audit-amfi-pmgr-contract.py pins for that kernelcache; scripts/build-fuxi-platform-power.py binds slots 320 and
321 to the same addresses before the link. This check reads the kernel that ships, so it replaces the prelinked
reference candidate UniXNU-sheng's build script reads before the link. --contract-only skips the bridge checks (for a
kernel built without CONFIG_XNU_SHENG_PMGR).
"""
import struct
import sys
from pathlib import Path

path = Path(sys.argv[1])
contract_only = '--contract-only' in sys.argv[2:]
data = path.read_bytes()
failures = 0


def check(cond, what):
    global failures
    print(('ok   ' if cond else 'FAIL ') + what)
    failures += not cond


magic, cpu, _, kind, ncmds = struct.unpack_from('<5I', data)
if (magic, cpu) != (0xfeedfacf, 0x0100000c):
    raise SystemExit(f'{path} is not an ARM64 Mach-O')
segments, symbols = [], {}
offset = 32
for _ in range(ncmds):
    cmd, size = struct.unpack_from('<II', data, offset)
    if cmd == 0x19:   # LC_SEGMENT_64
        vmaddr, vmsize, fileoff, filesize = struct.unpack_from('<4Q', data, offset + 24)
        segments.append((vmaddr, filesize, fileoff))
    elif cmd == 0x2:   # LC_SYMTAB
        symoff, nsyms, stroff, _ = struct.unpack_from('<4I', data, offset + 8)
        for i in range(nsyms):
            strx, ntype, _, _, value = struct.unpack_from('<IBBHQ', data, symoff + i * 16)
            if ntype & 0x0e == 0x0e and value:   # N_SECT: defined in a section
                end = data.index(b'\0', stroff + strx)
                symbols.setdefault(data[stroff + strx:end].decode('ascii', 'replace'), value)
    offset += size
names = {}
for name, value in symbols.items():
    names.setdefault(value, []).append(name)


def read(va, size):
    for vmaddr, filesize, fileoff in segments:
        if vmaddr <= va and va + size <= vmaddr + filesize:
            return data[fileoff + va - vmaddr:fileoff + va - vmaddr + size]
    raise SystemExit(f'{va:#x} is not file-backed in {path.name}')


def words(va, count):
    return struct.unpack(f'<{count}I', read(va, 4 * count))


def pointer(va):
    return struct.unpack('<Q', read(va, 8))[0]


def constructor_vptr(pc):
    """ADRP x8 / ADD x8 / STR x8, [x0]: the vtable address a constructor stores (as the UniXNU audit decodes it)."""
    first, second, store = words(pc, 3)
    if not (first & 0x9f00001f == 0x90000008 and second & 0xffc003ff == 0x91000108 and store == 0xf9000008):
        return None
    imm = ((first >> 5) & 0x7ffff) << 2 | ((first >> 29) & 3)
    if imm & (1 << 20):
        imm -= 1 << 21
    return (pc & ~4095) + (imm << 12) + ((second >> 10) & 4095)


# The contract inside the prelinked kexts (UniXNU scripts/audit-amfi-pmgr-contract.py).
NUB_READ, NUB_WRITE = 0xfffffff004a24adc, 0xfffffff004a230ec
AON_READ, AON_WRITE = 0xfffffff004a20fbc, 0xfffffff004a20fc4
check(read(0xfffffff0042dde02, 13) == b'ApplePMGRNub\0', 'AMFI matches the service class ApplePMGRNub')
check(pointer(0xfffffff005cfac08) == NUB_READ and pointer(0xfffffff005cfac10) == NUB_WRITE,
      'AMFI imports the nub read and write helpers')
check(words(0xfffffff004aaeb40, 5) == (0x94006c46, 0x321e0015, 0xaa1403e0, 0xaa1503e1, 0x94006c45),
      'AMFI reads through the nub, ORs bit 2 and writes the value back')
check(words(NUB_READ, 7) == (0xf9404400, 0xb4000080, 0xf9400008, 0xf9450101, 0xd61f0020, 0x12800000, 0xd65f03c0),
      'nub read: provider at +0x88, slot 320 (0xa00), 0xffffffff without a provider')
check(words(NUB_WRITE, 6) == (0xf9404400, 0xb4000080, 0xf9400008, 0xf9450502, 0xd61f0040, 0xd65f03c0),
      'nub write: provider at +0x88, slot 321 (0xa08), no operation without a provider')
base = constructor_vptr(0xfffffff0049f0058)
check(base == 0xfffffff005ce26d8, f'ApplePMGR constructor stores its vtable {base and hex(base)}')
check(base is not None and struct.unpack('<2Q', read(base + 320 * 8, 16)) == (AON_READ, AON_WRITE),
      'ApplePMGR slots 320 and 321 are its own AON read and write')
check(words(AON_READ, 3) == (0x12800000, 0xd65f03c0, 0xd65f03c0),
      'ApplePMGR AON read returns 0xffffffff, AON write returns at once')

if not contract_only:
    vtable, native, run = symbols.get('__ZTV18ShengPlatformPower'), symbols.get('__ZTV6IOPMGR'), symbols.get('_sheng_pmgr_run')
    check(bool(vtable and native and run), 'ShengPlatformPower, the IOPMGR vtable and sheng_pmgr_run are in the kernel')
    if vtable and native and run:
        own, inherited, original = 0, 0, 0
        for slot in range(340):
            entry = pointer(vtable + 16 + slot * 8)
            if slot in (320, 321):
                original += entry == (AON_READ, AON_WRITE)[slot - 320]
            elif slot in (0, 1, 7) or slot >= 168:
                own += any('18ShengPlatformPower' in n for n in names.get(entry, []))
            else:
                inherited += entry == pointer(native + 16 + slot * 8)
        check(original == 2, 'provider slots 320 and 321 are ApplePMGR\'s AON implementations')
        check(own == 3 + (340 - 168 - 2), f'lifecycle and every power slot are ShengPlatformPower\'s own guards ({own})')
        check(inherited == 168 - 3, f'the other slots are the native IOPMGR entries ({inherited})')
        # bsd_init calls the bridge (UniXNU-sm8550-common patches/xnu/sheng-platform-power.patch).
        start = symbols['_bsd_init']
        end = min(v for v in names if v > start)
        calls = [pc for pc in range(start, end, 4)
                 if (w := words(pc, 1)[0]) >> 26 == 0x25
                 and pc + ((w & 0x3ffffff) - (1 << 26) if w & (1 << 25) else w & 0x3ffffff) * 4 == run]
        check(len(calls) == 1, f'bsd_init calls sheng_pmgr_run ({len(calls)} call)')

print('PMGR bridge check:', 'all passed' if not failures else f'{failures} failed')
sys.exit(failures != 0)
