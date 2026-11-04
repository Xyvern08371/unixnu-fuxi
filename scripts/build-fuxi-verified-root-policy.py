#!/usr/bin/env python3
"""Prepare the two signed VerifiedRoot policies for fuxi's union SystemOS boot.

The kernel step links NativeVirtioBlock with NATIVE_VERIFIED_BLOCK_MULTI_POLICY
and links build-verified-root-probe.py --include-systemos. Both need the real
signed manifests below build/:

    build/verified-root-os/manifest.bin
    build/verified-root-systemos/manifest.bin

This script makes them from the unchanged IPSW disk images already cached under
out/ipsw/21H461. The OS and SystemOS windows in userdata-root.img are the same
bytes; the probes compare against the recorded raw-image SHA-256s.
"""
import argparse
import hashlib
import importlib.util
import json
import plistlib
import re
import subprocess
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = '21H461'
OS_DMG = '044-76040-038.dmg'
SYSTEMOS_DMG = '044-76034-038.dmg'
OS_UUID = uuid.UUID('04769D26-2CA0-4825-B443-E2E5F88300F2')
SYSTEMOS_UUID = uuid.UUID('8846FE78-2910-4297-AF97-D59BB6F8FC16')
OS_COMPRESSED_SHA256 = '3f99b859c9728379110b66657c7b15285bcb1925ad8b5726542e2cdcf8b1028d'
OS_IMAGE_SHA256 = 'e5634d04a8ac35f024845f583394e0a35deb26a04cb0c00286a8674e25a9a4f2'
SYSTEMOS_COMPRESSED_SHA256 = 'b4908cde41d23e6bc05e6af51a2c9eeb00cf0f863a6a18b1600c96a3fd70414f'
SYSTEMOS_IMAGE_SHA256 = SYSTEMOS_COMPRESSED_SHA256
OS_BYTES = 6077580800
SYSTEMOS_BYTES = 3303014400


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def image_size(dmg):
    info = subprocess.run(['hdiutil', 'imageinfo', '-plist', str(dmg)],
                          capture_output=True, check=True).stdout
    return plistlib.loads(info)['Size Information']['Total Bytes']


def attach(dmg):
    out = subprocess.run(['hdiutil', 'attach', '-nomount', '-readonly', '-noverify',
                          '-noautofsck', str(dmg)], capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        match = re.match(r'(/dev/disk\d+)\s', line)
        if match:
            return match.group(1)
    raise SystemExit(f'could not find the attached device for {dmg}')


def detach(device):
    subprocess.run(['hdiutil', 'detach', device], capture_output=True, check=True)


def ensure_keys(keys):
    keys.mkdir(parents=True, exist_ok=True)
    private, public = keys / 'owner.pem', keys / 'owner-public.pem'
    if private.is_file() and public.is_file():
        return private, public
    subprocess.run(['openssl', 'genrsa', '-out', str(private), '3072'], check=True)
    subprocess.run(['openssl', 'rsa', '-in', str(private), '-pubout', '-out', str(public)], check=True)
    return private, public


def make_policy(dmg, compressed_sha256, image_sha256, image_bytes, volume_uuid, output, keys,
                private_key, public_key, write_samples):
    if sha256_file(dmg) != compressed_sha256:
        raise SystemExit(f'{dmg.name} differs from the recorded IPSW sha256')
    if image_size(dmg) != image_bytes:
        raise SystemExit(f'{dmg.name} does not expand to the recorded {image_bytes} bytes')

    expected = output / 'verification.json'
    if expected.is_file():
        record = json.loads(expected.read_text())
        if (record.get('image_sha256') == image_sha256 and record.get('blocks_verified') ==
                (image_bytes + 4095) // 4096 and record.get('trusted_key_sha256')):
            print(f'{output.name}: policy already present ({image_sha256[:16]}...)')
            return

    spec = importlib.util.spec_from_file_location('verified_manifest',
                                                  ROOT / 'kits/VerifiedRoot/tools/manifest.py')
    manifest_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(manifest_module)

    output.mkdir(parents=True, exist_ok=True)
    device = attach(dmg)
    raw = Path(device.replace('/dev/disk', '/dev/rdisk'))
    try:
        with raw.open('rb', buffering=1024 * 1024) as stream:
            made = manifest_module.make(stream, image_bytes, private_key, public_key,
                                        volume_uuid, 1, output)
    finally:
        detach(device)

    if made['image_sha256'] != image_sha256:
        raise SystemExit(f'{output.name}: raw image digest {made["image_sha256"]} != {image_sha256}')

    block_count = made['block_count']
    indices = [0, 1, block_count // 2, block_count - 1]
    lengths = [4096, 4096, 4096, image_bytes - (block_count - 1) * 4096]
    if write_samples:
        device = attach(dmg)
        raw = Path(device.replace('/dev/disk', '/dev/rdisk'))
        try:
            with raw.open('rb', buffering=0) as stream:
                blocks = []
                for index, length in zip(indices, lengths):
                    stream.seek(index * 4096)
                    data = stream.read(length)
                    if len(data) != length:
                        raise SystemExit(f'short sample read at block {index}')
                    blocks.append(data.ljust(4096, b'\0'))
                (output / 'original-samples.bin').write_bytes(b''.join(blocks))
        finally:
            detach(device)

    record = dict(image_bytes=image_bytes, blocks_verified=block_count, image_sha256=made['image_sha256'],
                  volume_uuid=str(volume_uuid).upper(), generation=made['generation'],
                  trusted_key_sha256=made['trusted_key_sha256'],
                  actual_sample_indices=indices, actual_sample_lengths=lengths,
                  real_c_signature_and_block_verification=True,
                  original_image_modified=False, boot_root_authenticated=False,
                  host_only=True, hardware_tested=False)
    expected.write_text(json.dumps(record, indent=2) + '\n')
    print(f'{output.name}: wrote signed policy for {block_count} blocks ({made["image_sha256"][:16]}...)')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ipsw-dir', type=Path, default=ROOT.parents[1] / 'ipsw' / BUILD,
                        help='directory containing 044-76040-038.dmg and 044-76034-038.dmg')
    args = parser.parse_args()

    ipsw = args.ipsw_dir
    if not (ipsw / OS_DMG).is_file() and (ROOT / '.cache/firmware/target-volumes' / OS_DMG).is_file():
        ipsw = ROOT / '.cache/firmware/target-volumes'
    if not (ipsw / OS_DMG).is_file() or not (ipsw / SYSTEMOS_DMG).is_file():
        raise SystemExit(f'OS/SystemOS DMGs not found under {ipsw}; run "unixnu ipsw fetch OS \\"Cryptex1,SystemOS\\"" first')

    keys = ROOT / 'build/verified-root-fuxi/keys'
    private_key, public_key = ensure_keys(keys)

    make_policy(ipsw / OS_DMG, OS_COMPRESSED_SHA256, OS_IMAGE_SHA256, OS_BYTES,
                OS_UUID, ROOT / 'build/verified-root-os', keys, private_key, public_key, True)
    make_policy(ipsw / SYSTEMOS_DMG, SYSTEMOS_COMPRESSED_SHA256, SYSTEMOS_IMAGE_SHA256, SYSTEMOS_BYTES,
                SYSTEMOS_UUID, ROOT / 'build/verified-root-systemos', keys, private_key, public_key, True)
    (ROOT / 'build/xnu/ios-obj/EXPORT_HDRS/libsa').mkdir(parents=True, exist_ok=True)
    subprocess.run(['python3', str(ROOT / 'scripts/build-verified-root-probe.py'),
                    '--component', 'os', '--include-systemos'], cwd=ROOT, check=True)
    print('PASS: OS and SystemOS VerifiedRoot policies and probe archive are ready')


if __name__ == '__main__':
    main()
