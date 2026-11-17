#!/bin/bash
# 在 macOS 上生成 20G APFS Data 卷种子，打包成 DBRDISK1（scratch-data-20g.img）
set -euo pipefail

SIZE_GB="${SIZE_GB:-20}"
VOL_UUID="FEE1FE9D-1C1D-42F9-9A12-0732FA326C30"
OUT="$(pwd)/out"
DMG="$OUT/data.dmg"
PACKED="$OUT/scratch-data-20g.img"
mkdir -p "$OUT"

echo "=== 1) 创建 ${SIZE_GB}G raw APFS（layout NONE = 未压缩 raw）==="
rm -f "$DMG"
hdiutil create -size "${SIZE_GB}g" -layout NONE -fs APFS -volname Data -ov "$DMG"

echo "=== 2) 挂载并写 skip-setup prefs ==="
ATTACH=$(hdiutil attach -nobrowse -noverify -noautofsck "$DMG")
echo "$ATTACH"
# 卷名固定为 Data，挂载点就是 /Volumes/Data；兜底从 attach 输出里解析
MNT="/Volumes/Data"
if [ ! -d "$MNT" ]; then
  MNT=$(echo "$ATTACH" | grep -oE '/Volumes/[A-Za-z0-9_ .-]+' | head -1)
fi
echo "挂载点: $MNT"
[ -n "$MNT" ] && [ -d "$MNT" ]

mkdir -p "$MNT/private/var/mobile/Library/Preferences"
mkdir -p "$MNT/private/var/containers/Shared/SystemGroup"
mkdir -p "$MNT/private/var/mobile/Library/Caches"

python3 - <<PY
import plistlib, os
base = "$MNT/private/var/mobile/Library/Preferences"
os.makedirs(base, exist_ok=True)
def put(name, values):
    p = os.path.join(base, name + '.plist')
    data = plistlib.load(open(p,'rb')) if os.path.exists(p) else {}
    data.update(values)
    plistlib.dump(data, open(p,'wb'))
    os.chmod(p, 0o600)
put('com.apple.purplebuddy', {'SetupDone': True, 'SetupFinishedAllSteps': True, 'SetupVersion': 11, 'daemonizeNeedsToRun': False})
put('com.apple.migration', {'LastSystemVersion': '21H16'})
put('com.apple.managedconfiguration.notbackedup', {'LockdownActivationIndicatesCloudConfigurationAvailable': False})
put('com.apple.springboard', {'BKNoWatchdogs': True, 'MCForceShowCloudConfigurationUI': False})
print('prefs 已写入')
PY

echo "=== 3) 卸载 ==="
hdiutil detach "$MNT" >/dev/null 2>&1 || true
sleep 2

echo "=== 4) patch Data 卷 UUID -> $VOL_UUID ==="
python3 - <<PY
import uuid
p = "$DMG"
d = bytearray(open(p,'rb').read())
i = d.find(b'APSB')
assert i >= 0, '找不到 APSB（volume superblock）'
print('APSB @ 0x%x, 原 0xd0 UUID = %s' % (i, uuid.UUID(bytes=bytes(d[i+0xD0:i+0xE0]))))
d[i+0xD0:i+0xE0] = uuid.UUID("$VOL_UUID").bytes
open(p,'wb').write(d)
print('新 0xd0 UUID = %s' % uuid.UUID(bytes=bytes(d[i+0xD0:i+0xE0])))
PY

echo "=== 5) packed DBRDISK1 ==="
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "$SCRIPT_DIR/packed_ramdisk.py" "$DMG" "$PACKED"

echo "=== 完成 ==="
ls -la "$PACKED"
python3 - <<PY
import sys
sys.path.insert(0, "$SCRIPT_DIR")
import packed_ramdisk as pr
logical, extents = pr.regions(open("$PACKED",'rb').read())
print('验证: logical=%.2f GiB, extents=%d' % (logical/2**30, len(extents)))
PY
