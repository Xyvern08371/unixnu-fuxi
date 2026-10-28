#!/usr/bin/env python3
"""Which Metal methods the target's QuartzCore can send to each kind of Metal object (static, reads only).

The selector references (__objc_selrefs) of the unchanged QuartzCore in the target's dyld shared cache, intersected with the method names
the Apple A10 driver's classes and their Metal ancestors implement (decoded with the same pinned metadata layouts as
audit-target-metal-device.py). A reference proves QuartzCore *can* send the message; whether the system UI's paths do is for a run to
show. Output: build/gpu-analysis/quartzcore-metal-calls.json (ignored) and a summary per object kind."""
import json
from pathlib import Path
import runpy
import struct

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/gpu-analysis'
device = runpy.run_path(str(ROOT / 'scripts/audit-target-metal-device.py'))
surface = runpy.run_path(str(ROOT / 'scripts/audit-metal-api-surface.py'), run_name='surface')
cls, symbol, pointer = device['cls'], device['symbol'], device['pointer']

# The A10 driver's concrete classes for each object kind; their ancestry reaches Metal's own base classes.
KINDS = {
    'device': 'AGXA10FamilyDevice', 'texture': 'AGXA10FamilyTexture', 'buffer': 'AGXA10FamilyBuffer',
    'heap': 'AGXA10FamilyHeap', 'command queue': 'AGXA10FamilyCommandQueue', 'command buffer': 'AGXA10FamilyCommandBuffer',
    'render encoder': 'AGXA10FamilyRenderContext', 'blit encoder': 'AGXA10FamilyBlitContext',
    'compute encoder': 'AGXA10FamilyComputeContext', 'render pipeline': 'AGXA10FamilyRenderPipeline',
    'compute pipeline': 'AGXA10FamilyComputePipeline', 'sampler': 'AGXA10FamilySampler',
    'depth stencil': 'AGXA10FamilyDepthStencilState',
    # Metal's own classes where the driver adds none.
    'library': '_MTLLibrary', 'function': '_MTLFunction', 'binary archive': '_MTLBinaryArchive',
}


def ancestry(name):
    try:
        address = symbol('_OBJC_CLASS_$_' + name)
    except SystemExit:
        return None
    chain = []
    while address and len(chain) < 16:
        item = cls(address)
        chain.append(item)
        address = item['superclass']
    return chain


def quartzcore_selrefs():
    cache_main, read, pointer_, cstring = surface['cache']()
    table, count = struct.unpack_from('<2Q', cache_main, 136)
    for i in range(count):
        _, va, _, name = struct.unpack_from('<16sQ2I', cache_main, table + 32 * i)
        title = cache_main[name:cache_main.find(b'\0', name)].decode()
        if title != '/System/Library/Frameworks/QuartzCore.framework/QuartzCore':
            continue
        header = read(va, 32)
        size, = struct.unpack_from('<I', header, 20)
        image = surface['macho'](header + read(va + 32, size))
        refs = set()
        for segment in image['segments']:
            for section in segment['sections']:
                if section['name'] == '__objc_selrefs':
                    for at in range(section['va'], section['va'] + section['size'], 8):
                        target = pointer_(at)
                        if target:
                            refs.add(cstring(target))
        return refs
    raise SystemExit('QuartzCore not in the cache')


refs = quartzcore_selrefs()
report = {'quartzcore_selector_references': len(refs), 'kinds': {}}
for kind, name in KINDS.items():
    chain = ancestry(name)
    if not chain:
        report['kinds'][kind] = {'class': name, 'missing': True}
        print('%-16s %s: class not found' % (kind, name))
        continue
    sent = {}
    for item in chain:
        if item['name'] == 'NSObject':
            continue
        for method in item['methods']:
            if method['selector'] in refs and method['selector'] not in sent:
                sent[method['selector']] = {'class': item['name'], 'encoding': method['encoding']}
    report['kinds'][kind] = {'class': name, 'ancestry': [c['name'] for c in chain], 'selectors': dict(sorted(sent.items()))}
    print('%-16s %-34s %4d selectors QuartzCore references' % (kind, ' -> '.join(c['name'] for c in chain[:3]), len(sent)))
OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'quartzcore-metal-calls.json').write_text(json.dumps(report, indent=1) + '\n')
