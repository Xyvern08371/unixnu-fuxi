import os
import struct

roots = [
    "E:\\fuxi",
    "E:\\download",
    "E:\\ios-on-fuxi",
    "C:\\Users\\徐智伟\\Downloads",
    "C:\\Users\\徐智伟\\Desktop",
    "E:\\",
]

seen = set()
rows = []
for root in roots:
    if not os.path.isdir(root):
        continue
    for dirpath, dirnames, files in os.walk(root):
        depth = dirpath[len(root):].count(os.sep)
        if depth > 3:
            dirnames[:] = []
            continue
        # 跳过巨大的目录
        dirnames[:] = [d for d in dirnames if d.lower() not in
                       ("node_modules", ".git", "windows", "program files",
                        "program files (x86)", "appdata", "$recycle.bin")]
        for fn in files:
            if not fn.lower().endswith((".img", ".bin")):
                continue
            p = os.path.join(dirpath, fn)
            if p in seen:
                continue
            seen.add(p)
            try:
                sz = os.path.getsize(p)
            except Exception:
                continue
            if sz < 2 * 1024 * 1024 or sz > 200 * 1024 * 1024:
                continue
            try:
                with open(p, "rb") as f:
                    d = f.read(32)
            except Exception:
                continue
            if d[:8] == b"ANDROID!":
                ksz, = struct.unpack_from("<I", d, 8)
                rows.append((p, sz, ksz))

print("  %-56s %12s %10s" % ("file", "size", "kernel_sz"))
for p, sz, ksz in sorted(rows, key=lambda r: r[1]):
    print("  %-56s %12d %10d" % (p, sz, ksz))
print("  total:", len(rows))
