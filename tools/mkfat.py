r"""造 FAT16 镜像，支持长文件名（LFN）。

不依赖 mkfs.fat / mtools：按 Microsoft FAT 规范写 BPB、FAT、根目录和数据区。
FAT16 在 32MB 以内够用。簇大小 2 扇区（1KB）。

为什么需要 LFN：UEFI 的 UniXNU 固定去打开 \EFI\UniXNU\unixnu.toml。
8.3 名字里扩展名最多 3 个字符，所以 "unixnu.toml" 会被截成 UNIXNU.TOM，
FatDxe 就打不开了。这里给放不进 8.3 的名字生成标准 LFN 目录项。

用法：
    mkfat.py <out.img> <size_mb>  name=path [name2=path2 ...]

名字里用 '/' 分目录，目录会自动创建。
"""

import struct
import sys

SECTOR = 512
ATTR_DIR = 0x10
ATTR_ARCHIVE = 0x20
ATTR_LFN = 0x0F


def lfn_checksum(name11):
    """FAT 规范里的 8.3 名字校验和。"""
    total = 0
    for c in name11:
        total = (((total & 1) << 7) + (total >> 1) + c) & 0xFF
    return total


def split_83(name):
    """把名字拆成 8.3 的 (base, ext)，并返回是否真的能放进去。"""
    if "." in name:
        base, ext = name.rsplit(".", 1)
    else:
        base, ext = name, ""

    def clean(s):
        out = []
        for ch in s.upper():
            if ch.isalnum() or ch in "$%'-_@~`!(){}^#&":
                out.append(ch)
            else:
                out.append("_")
        return "".join(out)

    b, e = clean(base), clean(ext)
    fits = len(b) <= 8 and len(e) <= 3 and b != "" and name == name.upper()
    return b[:8].ljust(8), e[:3].ljust(3), fits


def lfn_entries(long_name, name11):
    """生成 long_name 的 LFN 目录项列表（按 FAT 要求的逆序）。"""
    csum = lfn_checksum(name11)
    chars = [ord(c) for c in long_name]
    # 补齐到 13 的倍数，用 0x0000 结束符再用 0xFFFF 填充
    if len(chars) % 13:
        chars.append(0x0000)
        while len(chars) % 13:
            chars.append(0xFFFF)

    chunks = [chars[i:i + 13] for i in range(0, len(chars), 13)]
    out = []
    for seq in range(len(chunks), 0, -1):
        c = chunks[seq - 1]
        e = bytearray(32)
        e[0] = seq | (0x40 if seq == len(chunks) else 0x00)
        pos = [1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30]
        for k in range(13):
            struct.pack_into("<H", e, pos[k], c[k])
        e[11] = ATTR_LFN
        e[12] = 0
        e[13] = csum
        struct.pack_into("<H", e, 26, 0)
        out.append(bytes(e))
    return out


def make_entry(long_name, attr, cluster, size):
    """生成完整的目录项：LFN（如果需要）+ 8.3 项。"""
    # . 和 .. 在 FAT 里就是全 0x20 填充的 8.3 名字，不能走常规拆分
    if long_name in (".", ".."):
        e = bytearray(32)
        raw = long_name.encode("ascii")
        e[0:len(raw)] = raw
        for k in range(len(raw), 11):
            e[k] = 0x20
        e[11] = attr
        struct.pack_into("<H", e, 26, cluster)
        struct.pack_into("<I", e, 28, size)
        return [bytes(e)]

    base, ext, fits = split_83(long_name)
    name11 = (base + ext).encode("ascii")

    entries = []
    if not fits:
        entries.extend(lfn_entries(long_name, name11))

    e = bytearray(32)
    e[0:8] = base.encode("ascii")
    e[8:11] = ext.encode("ascii")
    e[11] = attr
    struct.pack_into("<H", e, 26, cluster)
    struct.pack_into("<I", e, 28, size)
    entries.append(bytes(e))
    return entries


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        return 1

    out_path = sys.argv[1]
    size_mb = int(sys.argv[2])
    items = []
    for a in sys.argv[3:]:
        name, path = a.split("=", 1)
        items.append((name.strip("/"), path))

    total_sectors = size_mb * 1024 * 1024 // SECTOR

    reserved = 1
    num_fats = 2
    root_entries = 512
    root_sectors = (root_entries * 32 + SECTOR - 1) // SECTOR
    spc = 2
    media = 0xF8

    fatsz = 1
    for _ in range(8):
        data_start = reserved + num_fats * fatsz + root_sectors
        clusters = (total_sectors - data_start) // spc
        new_fatsz = ((clusters + 2) * 2 + SECTOR - 1) // SECTOR
        if new_fatsz == fatsz:
            break
        fatsz = new_fatsz

    data_start = reserved + num_fats * fatsz + root_sectors
    data_sectors = total_sectors - data_start
    clusters = data_sectors // spc
    assert 4085 < clusters < 65525, "簇数 %d 不落在 FAT16 范围" % clusters

    img = bytearray(total_sectors * SECTOR)

    # ---- BPB ----
    bpb = bytearray(SECTOR)
    bpb[0:3] = b"\xEB\x3C\x90"
    bpb[3:11] = b"MSDOS5.0"
    struct.pack_into("<H", bpb, 11, SECTOR)
    bpb[13] = spc
    struct.pack_into("<H", bpb, 14, reserved)
    bpb[16] = num_fats
    struct.pack_into("<H", bpb, 17, root_entries)
    struct.pack_into("<H", bpb, 19, total_sectors if total_sectors < 65536 else 0)
    bpb[21] = media
    struct.pack_into("<H", bpb, 22, fatsz)
    struct.pack_into("<H", bpb, 24, 32)
    struct.pack_into("<H", bpb, 26, 64)
    struct.pack_into("<I", bpb, 28, 0)
    struct.pack_into("<I", bpb, 32, total_sectors if total_sectors >= 65536 else 0)
    bpb[36] = 0x80
    bpb[38] = 0x29
    struct.pack_into("<I", bpb, 39, 0x12345678)
    bpb[43:54] = b"UNIXNU     "
    bpb[54:62] = b"FAT16   "
    bpb[510:512] = b"\x55\xAA"
    img[0:SECTOR] = bpb

    # ---- FAT ----
    fat = bytearray(fatsz * SECTOR)
    struct.pack_into("<HH", fat, 0, 0xFFF8, 0xFFFF)
    next_free = 2

    def alloc_chain(nbytes):
        nonlocal next_free
        need = max(1, (nbytes + spc * SECTOR - 1) // (spc * SECTOR))
        first = next_free
        for k in range(need):
            c = first + k
            struct.pack_into("<H", fat, c * 2, 0xFFFF if k == need - 1 else c + 1)
        next_free += need
        return first

    def cluster_off(c):
        return (data_start + (c - 2) * spc) * SECTOR

    # ---- 目录树 ----
    dirs = {""}
    for name, _ in items:
        parts = name.split("/")
        for k in range(1, len(parts)):
            dirs.add("/".join(parts[:k]))

    dir_clusters = {}
    for d in sorted(dirs):
        if d == "":
            continue
        dir_clusters[d] = alloc_chain(spc * SECTOR)

    def dir_region(dirpath):
        if dirpath == "":
            return reserved * SECTOR + num_fats * fatsz * SECTOR, root_entries * 32
        return cluster_off(dir_clusters[dirpath]), spc * SECTOR

    def add_entries(dirpath, entries, label):
        base_off, region = dir_region(dirpath)
        need = len(entries) * 32
        used = 0
        while used + 32 <= region and img[base_off + used] != 0:
            used += 32
        if used + need > region:
            raise RuntimeError("目录 %r 放不下 %r" % (dirpath, label))
        for e in entries:
            img[base_off + used:base_off + used + 32] = e
            used += 32

    # 子目录的 . 和 ..
    for d, c in dir_clusters.items():
        parent = d.rsplit("/", 1)[0] if "/" in d else ""
        pcluster = 0 if parent == "" else dir_clusters[parent]
        off = cluster_off(c)
        img[off:off + 32] = make_entry(".", ATTR_DIR, c, 0)[-1]
        img[off + 32:off + 64] = make_entry("..", ATTR_DIR, pcluster, 0)[-1]

    # 目录项
    for d in sorted(dirs):
        if d == "":
            continue
        parent = d.rsplit("/", 1)[0] if "/" in d else ""
        leaf = d.rsplit("/", 1)[-1]
        add_entries(parent, make_entry(leaf, ATTR_DIR, dir_clusters[d], 0), leaf)

    # 文件
    for name, path in items:
        data = open(path, "rb").read()
        first = alloc_chain(len(data))
        off = cluster_off(first)
        img[off:off + len(data)] = data
        parent = name.rsplit("/", 1)[0] if "/" in name else ""
        leaf = name.rsplit("/", 1)[-1]
        add_entries(parent, make_entry(leaf, ATTR_ARCHIVE, first, len(data)), leaf)
        print("  %-40s %9d 字节  簇 %d" % (name, len(data), first))

    fat_bytes = bytes(fat)
    assert len(fat_bytes) == fatsz * SECTOR
    img[reserved * SECTOR:(reserved + fatsz) * SECTOR] = fat_bytes
    img[(reserved + fatsz) * SECTOR:(reserved + 2 * fatsz) * SECTOR] = fat_bytes

    with open(out_path, "wb") as f:
        f.write(img)
    print("\n%s: %d 字节 (%.1f MB), FAT16, %d 簇, 已用 %d 簇"
          % (out_path, len(img), len(img) / 1048576, clusters, next_free - 2))
    return 0


if __name__ == "__main__":
    sys.exit(main())