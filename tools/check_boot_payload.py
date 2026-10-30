"""逐层解包 boot.img：gzip -> EFI FV -> LZMA 压缩段 -> FVMAIN，找 XNU payload。"""

import lzma
import struct
import sys
import zlib

path = sys.argv[1] if len(sys.argv) > 1 else r"E:\download\fuxi-uefi-134\edk2-msm\boot-fuxi.img"
img = open(path, "rb").read()

h = img.find(b"\x1f\x8b\x08")
d = zlib.decompressobj(31)
fv = d.decompress(img[h:]) + d.flush()
print(f"外层 gzip -> {len(fv):,} 字节")

# EFI_LZMA_CUSTOM_DECOMPRESS_GUID（混合端序）
guid = bytes.fromhex("98584eee143959429d6edc7bd79403cf")
poses = []
i = 0
while True:
    i = fv.find(guid, i)
    if i < 0:
        break
    poses.append(i)
    i += 16
print("LZMA 压缩段 GUID 命中:", [hex(p) for p in poses])

inner = None
for p in poses:
    usize, = struct.unpack_from("<I", fv, p + 16)
    try:
        data = lzma.decompress(fv[p + 20:], format=lzma.FORMAT_ALONE)
    except Exception as exc:
        print(f"  段@0x{p:x} 解压失败: {str(exc)[:50]}")
        continue
    print(f"  段@0x{p:x} -> {len(data):,} 字节 (声明 {usize:,})")
    for pat, name in ((b"_FVH", "FV"), (b"FUXIPAY1", "FUXIPAY1"), (b"CODE@ENTRY", "loader str")):
        pos = data.find(pat)
        print(f"     {name:10s}: {hex(pos) if pos != -1 else '无'}")
    inner = data

if inner is None:
    print("没有解出内层")
    sys.exit(1)

# 内层里找 payload
pos = inner.find(b"FUXIPAY1")
if pos < 0:
    print("内层里没有 FUXIPAY1（说明 payload 没被注进去）")
    sys.exit(2)

plen, = struct.unpack_from("<Q", inner, pos + 8)
payload = inner[pos + 16:pos + 16 + plen]
print(f"payload: {len(payload):,} 字节")

m, ver, nsegs = struct.unpack_from("<8sII", payload, 0)
virt_base, entry_va, adt_off, adt_size, kernel_end, phys_base, mem_size = \
    struct.unpack_from("<7Q", payload, 0x10)
print(f"magic={m} ver={ver} nsegs={nsegs} entry_va=0x{entry_va:x} phys_base=0x{phys_base:x}")

for k in range(nsegs):
    vmaddr, vmsize, foff, fsize = struct.unpack_from("<4Q", payload, 0x2A8 + 32 * k)
    if vmaddr <= entry_va < vmaddr + fsize:
        off = foff + (entry_va - vmaddr)
        w0, w1 = struct.unpack_from("<2I", payload, off)
        print(f"入口段 {k}: 0x{w0:08X} 0x{w1:08X}")
        if (w0 & 0xFC000000) == 0x14000000:
            imm = w0 & 0x03FFFFFF
            if imm & 0x02000000:
                imm -= 0x04000000
            print(f"  第一条 = b +0x{imm*4:X}   (新内核=0x1C28, 旧内核=0x1BD4)")
        break

print("payload 里品红 0x00FF00FF:", payload.count(struct.pack("<I", 0x00FF00FF)))
