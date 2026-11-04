"""用「我们的打包器 + 已知能启动的 UEFI 内核」重打一份 boot.img，验证容器是否合规。"""

import gzip
import zlib
import io
import struct
import subprocess
import sys

SRC = r"E:\download\fuxi-uefi-147\edk2-msm\boot-fuxi.img"
RAW = r"E:\download\uefi-kernel.bin"
GZ = r"E:\download\uefi-kernel.gz"
OUT = r"E:\download\test-repack.img"

d = io.open(SRC, "rb").read()
ks, ka, rs, ra, ss, sa, ta, pg, hv, osv = struct.unpack_from("<10I", d, 8)
print(f"UEFI 镜像: page={pg} kernel_size={ks} kernel_addr=0x{ka:x}")

gz = d[pg:pg + ks]
assert gz[:3] == b"\x1f\x8b\x08", gz[:4].hex()
d_o = zlib.decompressobj(31)
raw = d_o.decompress(gz) + d_o.flush()   # 忽略末尾的页对齐零
print(f"  解压后 {len(raw):,} 字节")

io.open(RAW, "wb").write(raw)

# 用 gzip -n -9 重新压缩（和 UEFI 那份一致的头部格式）
gz2 = gzip.compress(raw, 9, mtime=0)
io.open(GZ, "wb").write(gz2)
print(f"  重新压缩 {len(gz2):,} 字节（原始 {ks:,}）")

r = subprocess.run([sys.executable, "tools/mkshim_bootimg.py",
                    "--kernel", GZ, "--output", OUT],
                   capture_output=True, text=True, cwd=r"E:\ios-on-fuxi")
print(r.stdout.strip())
if r.returncode != 0:
    print(r.stderr.strip()[:500])
    sys.exit(1)
print("已生成", OUT)
