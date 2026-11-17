#!/bin/bash
# macOS: 删 MobileGestalt 缓存（强制 iOS 从新 ADT 的 model 重建）+ 改 hasDynamicIsland
set -eux
cd "$(dirname "$0")"

echo "=== 1. 解包 20G packed ==="
python3 - <<'PY'
import struct
src = 'seed20/scratch-data-20g.img'
dst = '/tmp/seed20.raw'
d = open(src, 'rb').read()
magic, ver, page, logical, count = struct.unpack_from('<8sIIQQ', d, 0)
assert magic == b'DBRDISK1'
extents = []
off = 32
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
print('raw written')
PY

echo "=== 2. attach + mount ==="
hdiutil attach -nomount -imagekey diskimage-class=CRawDiskImage /tmp/seed20.raw > /tmp/attach.txt 2>&1 || true
cat /tmp/attach.txt
VOL=$(grep -oE '/dev/disk[0-9]+s1' /tmp/attach.txt | tail -1)
echo "VOL=$VOL"
[ -n "$VOL" ] || exit 1
diskutil mount "$VOL"
sleep 2
ls /Volumes/

echo "=== 3. 找 MobileGestalt 缓存 ==="
SG=/Volumes/Data/containers/Shared/SystemGroup
ls -la "$SG" 2>/dev/null | head -10
MG_CACHE="$SG/systemgroup.com.apple.mobilegestaltcache/Library/Caches"
ls -la "$MG_CACHE" 2>/dev/null

echo "=== 4. 删除 MobileGestalt 缓存（强制重建）==="
if [ -d "$MG_CACHE" ]; then
  rm -fv "$MG_CACHE"/com.apple.MobileGestalt.plist 2>&1 || true
  echo "=== 剩余 ==="
  ls -la "$MG_CACHE" 2>/dev/null
else
  echo "NO CACHE DIR"
fi

echo "=== 5. 也看 preferences 的 ==="
ls -la /Volumes/Data/preferences/SystemConfiguration/com.apple.mobilegestalt.plist 2>/dev/null || echo "no prefs plist"

echo "=== 6. detach + pack ==="
diskutil unmount force "/Volumes/Data" 2>&1 || true
hdiutil detach /dev/disk7 -force 2>&1 || true
hdiutil detach /dev/disk8 -force 2>&1 || true
python3 packed_ramdisk.py /tmp/seed20.raw /tmp/seed20-mg2.img
mkdir -p out
cp /tmp/seed20-mg2.img out/scratch-data-20g.img
ls -la out/
