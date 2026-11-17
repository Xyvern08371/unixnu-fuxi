#!/bin/bash
# macOS: 解包 48G packed -> raw -> diskutil apfs resizeContainer 20G -> 打包
set -eux
cd "$(dirname "$0")"

echo "=== 1. 解包 48G packed seed（header=32 字节）==="
python3 - <<'PY'
import struct
src = 'seed/scratch-data.img'
dst = '/tmp/seed48.raw'
d = open(src, 'rb').read()
magic, ver, page, logical, count = struct.unpack_from('<8sIIQQ', d, 0)
assert magic == b'DBRDISK1', magic
print('logical=%d (%.2f GiB), extents=%d' % (logical, logical/2**30, count))
extents = []
off = 32   # header = 8+4+4+8+8 = 32
for i in range(count):
    e_off, e_len = struct.unpack_from('<QQ', d, off)
    off += 16
    extents.append((e_off, e_len))
data_off = 32 + count*16
out = open(dst, 'wb')
for e_off, e_len in extents:
    out.seek(e_off)
    out.write(d[data_off:data_off+e_len])
    data_off += e_len
out.truncate(logical)
out.close()
print('raw written:', dst)
PY
ls -la /tmp/seed48.raw
python3 - <<'PY'
import struct
f = open('/tmp/seed48.raw','rb')
d = f.read(0x1000)
i = d.find(b'NXSB')
print('NXSB @0x%x block_count =' % i, struct.unpack_from('<Q', d, i+8)[0])
f.close()
PY

echo "=== 2. hdiutil attach 裸 APFS raw ==="
hdiutil attach -nomount -imagekey diskimage-class=CRawDiskImage /tmp/seed48.raw > /tmp/attach.txt 2>&1 || true
cat /tmp/attach.txt
DEV=$(grep -oE '/dev/disk[0-9]+' /tmp/attach.txt | head -1)
echo "DEV=$DEV"
test -n "$DEV"
diskutil list "$DEV" || true

echo "=== 3. diskutil apfs resizeContainer 到 20G ==="
diskutil apfs resizeContainer "$DEV" 20g

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
python3 packed_ramdisk.py /tmp/seed48.raw /tmp/seed20.img
mkdir -p out
cp /tmp/seed20.img out/scratch-data-20g.img
ls -la out/
