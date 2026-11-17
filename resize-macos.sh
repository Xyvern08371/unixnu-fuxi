#!/bin/bash
# 在 macOS 上用 diskutil resizeVolume 把 48G APFS seed 缩到 20G（正规缩容）
set -eux
cd "$(dirname "$0")"

echo "=== 0. 查看 packed_ramdisk.py CLI ==="
python3 packed_ramdisk.py --help 2>&1 | head -20 || true

echo "=== 1. 解包 48G packed seed 成 raw ==="
python3 packed_ramdisk.py unpack seed/scratch-data.img /tmp/seed48.raw
ls -la /tmp/seed48.raw
python3 - <<'PY'
import struct
f = open('/tmp/seed48.raw','rb')
d = f.read(0x1000)
i = d.find(b'NXSB')
print('NXSB block_count =', struct.unpack_from('<Q', d, i+8)[0])
f.close()
PY

echo "=== 2. hdiutil attach 裸 APFS raw ==="
hdiutil attach -nomount -imagekey diskimage-class=CRawDiskImage /tmp/seed48.raw > /tmp/attach.txt 2>&1 || true
cat /tmp/attach.txt
DEV=$(grep -oE '/dev/disk[0-9]+' /tmp/attach.txt | head -1)
echo "DEV=$DEV"
test -n "$DEV"

echo "=== 3. diskutil resizeVolume 到 20G ==="
diskutil resizeVolume "$DEV" 20g

echo "=== 4. detach ==="
hdiutil detach "$DEV" -force || true

echo "=== 5. 验证 NXSB block_count ==="
python3 - <<'PY'
import struct
f = open('/tmp/seed48.raw','rb')
d = f.read(0x1000)
i = d.find(b'NXSB')
bc = struct.unpack_from('<Q', d, i+8)[0]
print('new block_count =', bc, '(%.2f GiB)' % (bc*4096/2**30))
f.close()
PY

echo "=== 6. 打包 packed ==="
python3 packed_ramdisk.py pack /tmp/seed48.raw /tmp/seed20.img
mkdir -p out
cp /tmp/seed20.img out/scratch-data-20g.img
ls -la out/
