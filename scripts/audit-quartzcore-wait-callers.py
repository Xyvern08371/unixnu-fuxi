#!/usr/bin/env python3
"""Locate direct calls to verified Objective-C wait/archive stubs in the exact target.

Read-only static analysis of the supplied ARM64 dyld cache. A callsite does not
prove execution frequency, workload, receiver class or a hardware latency cause.
No Apple executable bytes are emitted. Results stay in ignored build/.
"""
import bisect
import hashlib
import json
from pathlib import Path
import re
import runpy
import struct

ROOT = Path(__file__).resolve().parents[1]
SELECTORS = {
    'waitUntilComplete', 'waitUntilCompleted', 'waitUntilScheduled', 'commitAndWaitUntilSubmitted',
    'addScheduledHandler:', 'addCompletedHandler:', 'newBinaryArchiveWithDescriptor:error:',
    'addRenderPipelineFunctionsWithDescriptor:error:', 'addComputePipelineFunctionsWithDescriptor:error:',
    'serializeToURL:error:', 'newRenderPipelineStateWithDescriptor:error:',
    'newRenderPipelineStateWithDescriptor:options:reflection:error:',
    'newComputePipelineStateWithDescriptor:options:reflection:error:',
    'newComputePipelineStateWithFunction:error:',
    'newComputePipelineStateWithFunction:options:reflection:error:',
}


def signed(value, bits):
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def adrp(pc, word):
    return (pc & ~4095) + (signed(((word >> 5) & 0x7ffff) * 4 + ((word >> 29) & 3), 21) << 12)


def direct_branch(pc, word):
    if word & 0xfc000000 not in (0x94000000, 0x14000000):
        return None
    return pc + signed(word & 0x3ffffff, 26) * 4


def main():
    surface = runpy.run_path(str(ROOT / 'scripts/audit-metal-api-surface.py'), run_name='surface')
    cache, read, pointer, cstring = surface['cache']()  # enforces exact supplied ordinary ARM64 cache UUID
    table, count = struct.unpack_from('<2Q', cache, 136)
    image = None
    for i in range(count):
        _, va, _, name = struct.unpack_from('<16sQ2I', cache, table + i * 32)
        if cache[name:cache.find(b'\0', name)] != b'/System/Library/Frameworks/QuartzCore.framework/QuartzCore':
            continue
        header = read(va, 32)
        image = surface['macho'](header + read(va + 32, struct.unpack_from('<I', header, 20)[0]))
        break
    if image is None:
        raise SystemExit('Target QuartzCore image missing')
    sections = [s for segment in image['segments'] for s in segment['sections']]
    stubs = {}
    for section in sections:
        if section['name'] != '__objc_stubs':
            continue
        raw = read(section['va'], section['size'])
        for offset in range(0, len(raw) - 19, 4):
            a, b, c, d, e = struct.unpack_from('<5I', raw, offset)
            if not (a & 0x9f00001f == 0x90000001 and b & 0xffc003ff == 0xf9400021 and
                    c & 0x9f00001f == 0x90000010 and d & 0xffc003ff in (0xf9400210, 0x91000210) and e == 0xd61f0200):
                continue
            address = section['va'] + offset
            selref = adrp(address, a) + ((b >> 10) & 4095) * 8
            selector = cstring(pointer(selref))
            if selector in SELECTORS:
                stubs[address] = selector
    if not stubs:
        raise SystemExit('No selected stubs match the verified original ADRP/LDR/BR shape')
    # Existing symbol metadata is only a naming hint, not a function-boundary proof.
    symbols_path = ROOT / 'build/gpu-analysis/qc-symbols.txt'
    symbols = []
    if symbols_path.is_file():
        for line in symbols_path.read_text().splitlines():
            match = re.match(r'0x([0-9a-f]+):\s+\([^)]*__TEXT\.__text\)\s+([^\t]+)\tQuartzCore$', line)
            if match:
                symbols.append((int(match[1], 16), match[2]))
    symbols.sort()
    symbol_addresses = [s[0] for s in symbols]
    calls, section_hashes = [], {}
    for section in sections:
        if section['name'] != '__text':
            continue
        raw = read(section['va'], section['size'])
        section_hashes[hex(section['va'])] = hashlib.sha256(raw).hexdigest()
        for offset in range(0, len(raw) - 3, 4):
            pc = section['va'] + offset
            word, = struct.unpack_from('<I', raw, offset)
            target = direct_branch(pc, word)
            if target not in stubs:
                continue
            call = dict(pc=hex(pc), stub=hex(target), selector=stubs[target], tail_branch=word >> 31 == 0)
            index = bisect.bisect_right(symbol_addresses, pc) - 1
            if index >= 0:
                address, name = symbols[index]
                call['preceding_symbol_hint'] = name
                call['distance_from_symbol_hint'] = pc - address
            calls.append(call)
    counts = {name: sum(c['selector'] == name for c in calls) for name in sorted(SELECTORS)}
    report = dict(evidence='static target-code analysis; no runtime or hardware observation',
                  cache_uuid=cache[88:104].hex(), text_section_sha256=section_hashes,
                  selector_stubs={hex(k): v for k, v in stubs.items()}, direct_call_counts=counts, calls=calls,
                  limitations=['Direct calls to recognized stubs only; indirect dispatch is not covered.',
                               'Preceding symbol metadata is a hint, not a decoded function boundary.',
                               'No dynamic call frequency, receiver-class, shader-coverage or timing proof.'])
    if symbols_path.is_file():
        report['symbol_metadata_sha256'] = hashlib.sha256(symbols_path.read_bytes()).hexdigest()
    out = ROOT / 'build/gpu-analysis/quartzcore-wait-callers.json'
    out.write_text(json.dumps(report, indent=2) + '\n')
    for name, count in counts.items():
        print('%3d direct static calls: %s' % (count, name))


if __name__ == '__main__':
    main()
