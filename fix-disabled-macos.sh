#!/bin/bash
# macOS: 解包 20G packed -> raw -> 挂载改 disabled.plist -> 重新打包
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
print('logical=%d, extents=%d' % (logical, count))
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
ls -la /tmp/seed20.raw

echo "=== 2. hdiutil attach ==="
hdiutil attach -nomount -imagekey diskimage-class=CRawDiskImage /tmp/seed20.raw > /tmp/attach.txt 2>&1 || true
cat /tmp/attach.txt
DEV=$(grep -oE '/dev/disk[0-9]+' /tmp/attach.txt | head -1)
echo "DEV=$DEV"

echo "=== 3. 挂载 Data 卷 ==="
diskutil mount "${DEV}s1" 2>&1 || true
sleep 2
ls /Volumes/ 2>/dev/null

echo "=== 4. 改 disabled.plist ==="
PLIST=/Volumes/Data/db/com.apple.xpc.launchd/disabled.plist
if [ -f "$PLIST" ]; then
  cat "$PLIST"
  cat > "$PLIST" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>com.apple.CommCenter</key>
	<true/>
	<key>com.apple.identityservicesd</key>
	<true/>
	<key>com.apple.watchdogd</key>
	<true/>
	<key>com.apple.gpsd</key>
	<true/>
</dict>
</plist>
XML
  echo "=== 新内容 ==="
  cat "$PLIST"
else
  echo "NOT FOUND: $PLIST"
  ls -la /Volumes/Data/db/com.apple.xpc.launchd/ 2>/dev/null || true
fi

echo "=== 5. detach ==="
diskutil unmount "/Volumes/Data" 2>&1 || true
hdiutil detach "$DEV" -force || true

echo "=== 6. 重新打包 ==="
python3 packed_ramdisk.py /tmp/seed20.raw /tmp/seed20-new.img
mkdir -p out
cp /tmp/seed20-new.img out/scratch-data-20g.img
ls -la out/
