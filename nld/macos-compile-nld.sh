#!/bin/bash
# macOS: 编译 NativeLegacyDisplay.o（用已经打包的依赖）
set -eux
cd /tmp
echo "=== 1. 解压依赖 ==="
tar xzf xnu-deps.tar.gz
cd tree
ls -la

echo "=== 2. 找 iPhoneOS SDK ==="
xcrun --sdk iphoneos --show-sdk-path
SDK=$(xcrun --sdk iphoneos --show-sdk-path)

echo "=== 3. 编译 NativeLegacyDisplay.cpp ==="
python3 - <<'PY'
import json, subprocess
T = '/tmp/tree'
cmd = json.load(open(T + '/build/native-legacy-display/compile-command.json'))
# 改成 macOS 的 clang
cmd[0] = 'xcrun'
cmd.insert(1, 'clang')
# 加 -isysroot（iPhoneOS SDK）
import os
sdk = subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'], text=True).strip()
# 在 -nostdlibinc 之后加 sysroot
if '-isysroot' not in cmd:
    cmd = cmd[:1] + ['-isysroot', sdk] + cmd[1:]
print('cmd len:', len(cmd))
r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
print('rc:', r.returncode)
if r.returncode != 0:
    print('stderr (last 4000):')
    print(r.stderr[-4000:])
else:
    print('✅ 编译成功')
PY
ls -la build/native-legacy-display/NativeLegacyDisplay.o 2>/dev/null || echo "NO .o"
