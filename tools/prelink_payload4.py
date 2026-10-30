#!/usr/bin/env python3
"""payload 层预链接 v4：组件**紧凑重排**后放进 kext 区。

为什么要重排：
  Apple 的 kernelcache 里组件按它们的布局分散在约 45MB 地址空间（真实数据约 19MB），
  而 virt_base 到 __TEXT 之间的 kext 区最多约 31MB。所以必须把组件段紧凑打包，
  并把所有指向组件的指针按"旧地址→新地址"映射重写。

流程：
  1. plan(slide=0)：组件仍在 Apple 原始地址上规划，拿到绑定表
  2. 紧凑打包：每个容器段内按原 VA 顺序、16K 对齐依次放置
  3. 建映射 old_va → new_va（逐段）
  4. 拷贝数据 + 重绑（site 和 component 目标都走映射；kernel 目标用 plan 解析结果）
  5. 改内核 Mach-O 的 __PRELINK_* 段表
"""

import io
import struct
import sys

sys.path.insert(0, r"E:\ios-on-fuxi\tools")
sys.path.insert(0, r"E:\download\UniXNU\kits\NativePrelink")

import mkpayload_fuxi as mp
from prelink_try2 import load_kc, normalize_info, tolerant_macho, strip_ctf, KC_KERNEL_OFF

KERNEL = sys.argv[1] if len(sys.argv) > 1 else r"E:\download\xnu-kernel-23\out\kernel.development.fuxi"
OUT = r"E:\download\payload-prelinked.bin"
ADT = sys.argv[2] if len(sys.argv) > 2 else r"E:\ios-on-fuxi\rom\xnu\fuxi.adt"
PAGE = 0x4000
CONTAINER_ORDER = ["__PRELINK_TEXT", "__PLK_TEXT_EXEC", "__PLK_DATA_CONST", "__PRELINK_DATA"]
COALESCED = {"__PRELINK_TEXT": "__TEXT", "__PLK_TEXT_EXEC": "__TEXT_EXEC",
             "__PLK_DATA_CONST": "__DATA_CONST", "__PRELINK_DATA": "__DATA"}


def align(x, a=PAGE):
    return (x + a - 1) & ~(a - 1)


def parse_payload(buf):
    magic, ver, nsegs = struct.unpack_from("<8sII", buf, 0)
    virt_base, entry, adt_off, adt_size, kernel_end, phys_base, mem_size = \
        struct.unpack_from("<7Q", buf, 0x10)
    cmdline = bytes(buf[0x48:0x48 + 608]).split(b"\0")[0].decode("latin1")
    segs = []
    for i in range(nsegs):
        vmaddr, vmsize, foff, fsize = struct.unpack_from("<4Q", buf, 0x2A8 + 32 * i)
        segs.append(dict(vmaddr=vmaddr, vmsize=vmsize, off=foff, size=fsize))
    return dict(virt_base=virt_base, entry=entry, adt_off=adt_off, adt_size=adt_size,
                kernel_end=kernel_end, phys_base=phys_base, mem_size=mem_size,
                cmdline=cmdline, segs=segs)


def patch_macho_segments(text_data: bytearray, updates: dict) -> int:
    magic, = struct.unpack_from("<I", text_data, 0)
    assert magic == 0xFEEDFACF, hex(magic)
    ncmds, = struct.unpack_from("<I", text_data, 16)
    p = 32
    done = 0
    for _ in range(ncmds):
        cmd, length = struct.unpack_from("<II", text_data, p)
        if cmd == 0x19 and length >= 72:
            name = bytes(text_data[p + 8:p + 24]).split(b"\0")[0].decode()
            if name in updates:
                va, vsize = updates[name]
                struct.pack_into("<Q", text_data, p + 24, va)
                struct.pack_into("<Q", text_data, p + 32, vsize)
                done += 1
        p += length
    return done


def main() -> int:
    import native_prelink as np
    np.macho = tolerant_macho

    print("① 基础 payload")
    base, _ = mp.build(KERNEL, ADT, "debug=0xc serial=3 cpus=1 keepsyms=1 -v kdp_match_name=none")
    p = parse_payload(base)
    text_va = p["segs"][0]["vmaddr"]
    region_lo = align(p["virt_base"])
    print(f"   virt_base=0x{p['virt_base']:x} __TEXT=0x{text_va:x} kext 区 {(text_va - region_lo) / 1048576:.1f} MB")

    print("② 规划（slide=0，组件保持 Apple 原始地址）")
    kc = load_kc()
    original = bytes(normalize_info(bytearray(kc[KC_KERNEL_OFF:])))
    native = bytes(strip_ctf(bytearray(io.open(KERNEL, "rb").read())))
    orig_kernel = tolerant_macho(original)

    r = np.plan(native, original, ["com.apple.filesystems.apfs"], 0)
    print(f"   组件 {len(r['components'])} 绑定 {r['pointer_counts']}")

    print("③ 紧凑打包")
    by_container = {c: [] for c in CONTAINER_ORDER}
    for e in r["extents"]:
        c = next((k for k, v in COALESCED.items() if v == e["segment"]), None)
        if c:
            by_container[c].append(e)

    new_segs = []
    mapping = []          # (old_lo, old_hi, delta)
    cursor = region_lo
    for cname in CONTAINER_ORDER:
        items = sorted(by_container.get(cname) or [], key=lambda i: i["va"])
        if not items:
            continue
        seg_va = cursor
        buf = bytearray()
        for it in items:
            at = align(len(buf))
            buf += b"\0" * (at - len(buf))
            oseg = next((s for s in orig_kernel["segments"]
                         if s["va"] <= it["va"] < s["va"] + s["size"]), None)
            if oseg:
                off_in = oseg["fileoff"] + it["va"] - oseg["va"]
                buf += original[off_in:off_in + it["size"]]
            new_va = seg_va + at
            mapping.append((it["va"], it["va"] + it["size"], new_va - it["va"]))
        vsize = align(len(buf))
        buf += b"\0" * (vsize - len(buf))
        new_segs.append(dict(name=cname, vmaddr=seg_va, vmsize=vsize, data=bytes(buf)))
        print(f"   {cname:<18} va=0x{seg_va:x} vsize=0x{vsize:x}")
        cursor = align(seg_va + vsize)

    if cursor > text_va:
        print(f"   ✗ 超出 kext 区（0x{cursor:x} > 0x{text_va:x}）")
        return 1
    print(f"   总计至 0x{cursor:x}，剩余 {(text_va - cursor) / 1048576:.1f} MB")

    def map_va(old):
        for lo, hi, delta in mapping:
            if lo <= old < hi:
                return old + delta
        return None

    print("④ 组装 payload")
    pieces = [(s["vmaddr"], s["vmsize"], bytes(base[s["off"]:s["off"] + s["size"]]), None)
              for s in p["segs"]]
    pieces += [(s["vmaddr"], s["vmsize"], s["data"], s["name"]) for s in new_segs]
    pieces.sort(key=lambda t: t[0])

    kernel_end = align(max(va + vs for va, vs, _, _ in pieces))
    hdr = 0x2A8 + 32 * len(pieces)
    out = bytearray(hdr)
    table = []
    for va, vs, data, name in pieces:
        off = len(out)
        out += data
        out += b"\0" * (-len(out) & 0xF)
        table.append((va, vs, off, len(data)))

    adt_off = len(out)
    out += base[p["adt_off"]:p["adt_off"] + p["adt_size"]]
    out += b"\0" * (-len(out) & 0xF)

    struct.pack_into("<8sII", out, 0, b"FUXIXNU", 1, len(pieces))
    struct.pack_into("<7Q", out, 0x10, p["virt_base"], p["entry"], adt_off, p["adt_size"],
                     kernel_end, p["phys_base"], p["mem_size"])
    cl = p["cmdline"].encode()[:607]
    out[0x48:0x48 + len(cl)] = cl
    for i, t in enumerate(table):
        struct.pack_into("<4Q", out, 0x2A8 + 32 * i, *t)
    print(f"   kernel_end=0x{kernel_end:x} {len(pieces)} 段 {len(out):,} 字节")

    print("⑤ 改内核 Mach-O 段表")
    # __TEXT 就是基础 payload 的第一个段（内核 Mach-O 所在），按 VA 精确定位
    tva = tvs = toff = tsize = None
    for va, vs, off, size in table:
        if va == text_va:
            tva, tvs, toff, tsize = va, vs, off, size
            break
    assert toff is not None, "找不到内核 __TEXT 段"
    text_data = bytearray(out[toff:toff + tsize])
    updates = {s["name"]: (s["vmaddr"], s["vmsize"]) for s in new_segs}
    n = patch_macho_segments(text_data, updates)
    out[toff:toff + tsize] = text_data
    print(f"   更新 {n} 个段")

    print("⑥ 重绑")
    applied = skipped = 0
    for b in r["bindings"]:
        new_site = map_va(b["site"])
        if new_site is None:
            skipped += 1
            continue
        target = b["new_target"]
        if b["kind"] == "component":
            mapped = map_va(target)
            if mapped is None:
                skipped += 1
                continue
            target = mapped
        # site 落在哪个段
        seg = next((s for s in new_segs
                    if s["vmaddr"] <= new_site < s["vmaddr"] + s["vmsize"]), None)
        if not seg:
            skipped += 1
            continue
        off = next(o for va, vs, o, size in table if va == seg["vmaddr"])
        foff = off + (new_site - seg["vmaddr"])
        if foff + 8 > len(out):
            skipped += 1
            continue
        struct.pack_into("<Q", out, foff, target)
        applied += 1
    print(f"   已重绑 {applied}，跳过 {skipped}")

    io.open(OUT, "wb").write(bytes(out))
    print(f"\n✅ {OUT}（{len(out):,} 字节）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
