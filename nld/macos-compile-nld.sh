#!/bin/bash
# macOS: 编译 NativeLegacyDisplay.o（用已经打包的依赖）
set -eux
cd /tmp
echo "=== 1. 解压依赖 ==="
tar xzf xnu-deps.tar.gz
ls -la

echo "=== 2. 找 iPhoneOS SDK ==="
SDK=$(xcrun --sdk iphoneos --show-sdk-path)
echo "SDK=$SDK"

echo "=== 3. 编译 NativeLegacyDisplay.cpp ==="
python3 - <<'PY'
import json, subprocess
T = '/tmp/tree'
cmd = json.load(open(T + '/build/native-legacy-display/compile-command.json'))
sdk = subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'], text=True).strip()
# xcrun clang -isysroot <sdk> <原始参数...>
cmd[0] = 'xcrun'
cmd.insert(1, 'clang')
cmd = cmd[:2] + ['-isysroot', sdk] + cmd[2:]
print('cmd len:', len(cmd))
print('head:', cmd[:6])
r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
print('rc:', r.returncode)
if r.returncode != 0:
    err = r.stderr
    lines = [l for l in err.splitlines() if 'error:' in l or 'fatal' in l]
    print('错误行数:', len(lines))
    print('\n'.join(lines[:25]))
else:
    print('✅ 编译成功')
PY
ls -la /tmp/tree/build/native-legacy-display/NativeLegacyDisplay.o 2>/dev/null || echo "NO .o"
