"""把 ios-sweet 的 shim 改造成 fuxi 版（常量替换 + 魔数替换）。

输出到 loader-shim-fuxi/，不影响现有 UEFI 加载器。
"""

import io
import os
import shutil

SRC = r"E:\download\ios-sweet\shim"
DST = r"E:\ios-on-fuxi\loader-shim-fuxi"

os.makedirs(DST, exist_ok=True)

FILES = ["start.S", "shim.c", "console.c", "console.h", "fdt.c", "fdt.h",
         "loader.c", "loader.h", "mmu.c", "mmu.h", "ufs.c", "ufs.h",
         "shim.ld", "font.h"]

# (旧, 新) —— 顺序重要：先长后短
REPLACE = [
    (b"0x9c000000", b"0xB0000000"),      # framebuffer
    (b"0x9C000000", b"0xB0000000"),
    (b"0x17a00000", b"0x17100000"),      # GICD  (sweet -> fuxi)
    (b"0x17A00000", b"0x17100000"),
    (b"0x17a60000", b"0x17180000"),      # GICR
    (b"0x17A60000", b"0x17180000"),
    (b"SWEETXNU", b"FUXIXNU"),           # payload magic
    (b"sweet-shim", b"fuxi-shim"),
]

for name in FILES:
    src = os.path.join(SRC, name)
    if not os.path.exists(src):
        print(f"  skip {name} (not found)")
        continue
    raw = io.open(src, "rb").read()
    for old, new in REPLACE:
        raw = raw.replace(old, new)
    io.open(os.path.join(DST, name), "wb").write(raw)
    print(f"  {name}: {len(raw):,} bytes")

print("\n替换后的关键常量：")
for name in ("console.h", "shim.c", "loader.c"):
    p = os.path.join(DST, name)
    if not os.path.exists(p):
        continue
    for i, line in enumerate(io.open(p, encoding="utf-8", errors="replace").read().split("\n"), 1):
        if any(k in line for k in ("FB_BASE", "GICD_BASE", "GICR_BASE", "FUXIXNU", "fuxi-shim")):
            print(f"  {name}:{i}: {line.strip()}")
