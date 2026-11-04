#!/usr/bin/env python3
"""Check a decrypted boot image of the Build workflow before it is started with fastboot boot.

usage: python3 ci/check-boot-image.py <boot.img> <boot.json> <uefi-fuxi checkout> [--fd-out FILE]

The expected values come from this repository's board.toml ([bootimg], [payload]) and the firmware checkout's device
config: the container header and load addresses, the shim's ARM64 header (text offset, an image size that covers the
payload), the firmware volume and the payload after it, the appended FdtBlob and the placeholder ramdisk. It then lists
the payload's FAT32 files, checks that the kernel carries the touch probe, prints the ADT root and /chosen values and
compares the boot menu's arguments with [payload] kernel_args. Exits non-zero on any mismatch. Nothing is written,
except with --fd-out: then the image's firmware volume goes to FILE once every check passed, so payload variants
(entry probes) can be packed with exactly the tested firmware (./unixnu bootimg --fd FILE).
"""
import argparse
import hashlib
import json
import struct
import sys
import tomllib
import zlib
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('image', type=Path)
parser.add_argument('report', type=Path)
parser.add_argument('uefi', type=Path)
parser.add_argument('--fd-out', type=Path, help='write the firmware volume here when every check passed')
options = parser.parse_args()
image_path, report_path, uefi = options.image, options.report, options.uefi
board = tomllib.loads((Path(__file__).resolve().parents[1] / 'board.toml').read_text())
spec = board['bootimg']['image']
config = tomllib.loads((uefi / 'Resources/Configs' / f'{board["firmware"]["config"]}.toml').read_text())
fd_size = config['uefi_fd']['size']
data = image_path.read_bytes()
report = json.loads(report_path.read_text())
failures = 0


def check(cond, what):
    global failures
    print(('ok   ' if cond else 'FAIL ') + what)
    failures += not cond


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


# Container: an Android boot image header (v0 for fastboot boot on fuxi).
kernel_size, kernel_addr, ramdisk_size, _, second_size, _, tags, page, version, _ = struct.unpack_from('<10I', data, 8)
check(data[:8] == b'ANDROID!' and version == spec['header_version'] and page == spec['pagesize'] and not second_size,
      f'header v{version}, page {page}, no second stage')
check(kernel_addr == spec['base'] + spec['kernel_offset'] and tags == spec['base'] + spec['tags_offset'],
      f'load addresses: kernel {kernel_addr:#x}, tags {tags:#x}')
check(sha(data) == report['image_sha256'] and len(data) == report['image_bytes'], f'image is the one boot.json describes ({len(data)} bytes)')

# Kernel: gzip(shim + firmware volume + payload) followed by the device tree.
region = data[page:page + kernel_size]
check(sha(region) == report['kernel_sha256'], 'kernel region matches boot.json')
unpacker = zlib.decompressobj(16 + zlib.MAX_WBITS)
image = unpacker.decompress(region)
check(unpacker.eof, 'gzip stream complete')
shim = report['shim_bytes']
text_offset, image_size = struct.unpack_from('<QQ', image, 8)
check(image[56:60] == b'ARM\x64' and text_offset == spec['text_offset'], f'ARM64 header, text offset {text_offset:#x}')
check(image_size == len(image) == shim + fd_size + report['payload_bytes'],
      f'image size {image_size:#x} = shim {shim:#x} + firmware {fd_size:#x} + payload {report["payload_bytes"]:#x}')
fd = image[shim:shim + fd_size]
check(sha(fd) == report['fd_sha256'] and fd[0x28:0x2c] == b'_FVH', 'firmware volume is the built FD')
payload = image[shim + fd_size:]
tree = unpacker.unused_data
fdt = (uefi / 'Platforms/Xiaomi/fuxiPkg/FdtBlob/sm8550-xiaomi-fuxi.dtb').read_bytes()
check(tree == fdt and sha(tree) == report['dtb_sha256'], 'appended device tree is the FdtBlob')
start = page * (1 + -(-kernel_size // page))
check(data[start:start + ramdisk_size] == (uefi / 'Resources/ramdisk').read_bytes(), 'ramdisk is the firmware placeholder')

# Payload: the FAT32 volume of ./unixnu build payload.
bps, spc, reserved, fats = struct.unpack_from('<HBHB', payload, 11)
fat_size, root = struct.unpack_from('<I', payload, 36)[0], struct.unpack_from('<I', payload, 44)[0]
label = payload[71:82].decode('ascii', 'replace').strip()
check(payload[510:512] == b'\x55\xaa' and bps == 512 and label == board['payload']['volume'][:11],
      f'payload FAT32 volume {label!r}, {len(payload) >> 20} MiB')
fat = payload[reserved * bps:(reserved + fat_size) * bps]
data_start, cluster_bytes = (reserved + fats * fat_size) * bps, spc * bps


def read(cluster, size=None):
    parts = []
    while 2 <= cluster < 0x0ffffff8:
        parts.append(payload[data_start + (cluster - 2) * cluster_bytes:data_start + (cluster - 1) * cluster_bytes])
        cluster = struct.unpack_from('<I', fat, cluster * 4)[0] & 0x0fffffff
    blob = b''.join(parts)
    return blob if size is None else blob[:size]


def walk(cluster, prefix, files):
    blob, long_name = read(cluster), []
    for offset in range(0, len(blob), 32):
        entry = blob[offset:offset + 32]
        if entry[0] == 0:
            break
        if entry[0] == 0xe5:
            long_name = []
        elif entry[11] == 0x0f:
            long_name.insert(0, (entry[1:11] + entry[14:26] + entry[28:32]).decode('utf-16-le').split('\0')[0])
        else:
            short = entry[0:8].decode('ascii').rstrip() + ('.' + entry[8:11].decode('ascii').rstrip() if entry[8:11].strip() else '')
            name, long_name = ''.join(long_name) or short, []
            if entry[11] & 0x08 or name in ('.', '..'):
                continue
            first = struct.unpack_from('<H', entry, 20)[0] << 16 | struct.unpack_from('<H', entry, 26)[0]
            if entry[11] & 0x10:
                walk(first, f'{prefix}{name}/', files)
            else:
                files[prefix + name] = (first, struct.unpack_from('<I', entry, 28)[0])
    return files


files = walk(root, '/', {})
for name, (_, size) in sorted(files.items()):
    print(f'     {name}  {size} bytes')
kernel = read(*files['/EFI/UniXNU/Payloads/kernel.macho']) if '/EFI/UniXNU/Payloads/kernel.macho' in files else b''
check(kernel[:4] == b'\xcf\xfa\xed\xfe', f'kernel.macho is a 64-bit Mach-O (sha256 {sha(kernel)[:16]})')
# The probe's boot argument names are strings of its own: present only when the probe is linked in.
check(all(name in kernel for name in (b'fuxi-touch\0', b'fuxi-touch-panic\0', b'fuxi-touch-tcs\0')), 'kernel carries the touch probe')


def adt_node(blob, offset, path, nodes):
    """Apple device tree node: nprops, nchildren, properties (name[32], length, value padded to 4), children."""
    nprops, nchildren = struct.unpack_from('<II', blob, offset)
    offset, props = offset + 8, {}
    for _ in range(nprops):
        length = struct.unpack_from('<I', blob, offset + 32)[0] & 0x7fffffff
        props[blob[offset:offset + 32].split(b'\0')[0].decode()] = blob[offset + 36:offset + 36 + length]
        offset += 36 + (length + 3) // 4 * 4
    name = props.get('name', b'').split(b'\0')[0].decode()
    here = f'{path}/{name}' if path or name != 'device-tree' else ''
    nodes[here or '/'] = props
    for _ in range(nchildren):
        offset = adt_node(blob, offset, here, nodes)
    return offset


adt, nodes = (read(*files['/EFI/UniXNU/Payloads/kernel.macho.adt']) if '/EFI/UniXNU/Payloads/kernel.macho.adt' in files else b''), {}
check(bool(adt) and adt_node(adt, 0, '', nodes) == len(adt), f'kernel.macho.adt parses ({len(nodes)} nodes)')
for path, prop in (('/', 'compatible'), ('/', 'model'), ('/chosen', 'chip-id'), ('/chosen', 'unique-chip-id'),
                   ('/chosen', 'dram-size'), ('/chosen', 'darwinboot-memory-size')):
    value = nodes.get(path, {}).get(prop)
    if value is None:
        shown = 'absent'
    elif value.rstrip(b'\0') and all(32 <= c < 127 or c == 0 for c in value.rstrip(b'\0')):
        shown = value.rstrip(b'\0').replace(b'\0', b' | ').decode()
    else:
        shown = hex(int.from_bytes(value, 'little'))
    print(f'     ADT {path} {prop}: {shown}')
menu = read(*files['/EFI/UniXNU/unixnu.toml']).decode() if '/EFI/UniXNU/unixnu.toml' in files else ''
entries = tomllib.loads(menu).get('entry', []) if menu else []
args = next((entry.get('args') for entry in entries if entry.get('id') == 'xnu'), None)
check(args == ' '.join(board['payload']['kernel_args']), f'boot menu entry xnu: {args}')

print('boot image check:', 'all passed' if not failures else f'{failures} failed')
if options.fd_out and not failures:
    options.fd_out.write_bytes(fd)
    print(f'firmware volume written to {options.fd_out} (sha256 {sha(fd)})')
sys.exit(failures != 0)
