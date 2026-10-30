#!/usr/bin/env python3
"""Drop (or restore) the board.toml archives that need prelink candidates.

usage: drop_prelink_archives.py BOARD.TOML phase1|restore
"""
import io
import pathlib
import re
import subprocess
import sys

board = pathlib.Path(sys.argv[1])
mode = sys.argv[2]
PRELINK_SCRIPTS = ('build-native-aes-bindings.py', 'build-native-legacy-display.py',
                   'build-native-mobile-display.py', 'build-sheng-platform-power.py',
                   'build-original-gpu-provider-probe.py', 'build-adreno740-kits.py',
                   'build-native-adreno-kits.py', 'build-native-adreno-accelerator.py')

if mode == 'restore':
    subprocess.run(['git', '-C', str(board.parent), 'checkout', '--', board.name], check=True)
    print('restored', board)
    sys.exit(0)

def patch_py(p):
    s = io.open(p, encoding='utf-8').read()
    if 'XNU_BOOT_PROGRESS=1 forced' not in s:
        return
    io.open(p, 'w', encoding='utf-8').write(s)

s = io.open(board, encoding='utf-8').read()
removed = []
for name in PRELINK_SCRIPTS:
    needle = '"%s"' % name
    if needle in s:
        s = re.sub(r'\n\s*"%s",' % re.escape(name), '', s)
        removed.append(name)
io.open(board, 'w', encoding='utf-8').write(s)
print('phase1 removed:', removed)