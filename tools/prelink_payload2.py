#!/usr/bin/env python3
"""payload 层预链接 v2：组件放在内核之上，virt_base 保持不变。

要点：
  · 不动 virt_base（实测下调会让内核早期 panic）
  · 组件容器段放到 kernel_end 之后（VA 往上长）
  · 内核对组件的映射来自内核自己的 Mach-O 段表，所以必须就地修改 payload 里
    那份 Mach-O 头中的 __PRELINK_* 段（内核里本来就有这几条零大小的记录）
  · 指针在 payload 数据里重绑
"""

import io
import struct
import sys

sys.path.insert(0, r"E:\ios-on-fuxi\tools")
sys.path.insert(0, r"E:\download\UniXNU\kits\NativePrelink")

import mkpayload_fuxi as mp
from prelink_try2 import load_kc, normalize_info, tolerant_macho, strip_ctf, KC_KERNEL_OFF

KERNEL = r"E:\download\xnu-kernel-22\out\kernel.development.fuxi"
ADT = r"E:\ios-on-fuxi\rom\xnu\fuxi.adt"
OUT = r"E:\download\payload-prelinked.bin"
PAGE = 0x4000
COALESCED = {"__PRELINK_TEXT": "__TEXT", "__PLK_TEXT_EXEC": "__TEXT_EXEC",
             "__PLK_DATA_CONST": "__DATA_CONST", "__PRELINK_DATA": "__DATA"}


def align(x, a=PAGE):
    return (x + a - 1) & ~(a - 1)


def parse_payload(buf):
    magic, ver, nsegs = struct.unpack_from("<8sII", buf, 0)
    assert magic == b"FUXIXNU\0", magic
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
    """在 payload 的 __TEXT 数据里就地修改内核 Mach-O 的段表"""
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
    base, info = mp.build(KERNEL, ADT, "debug=0xc serial=3 cpus=1 keepsyms=1 -v kdp_match_name=none")
    p = parse_payload(base)
    print(f"   {len(base):,} 字节，{len(p['segs'])} 段，virt_base=0x{p['virt_base']:x}，"
          f"kernel_end=0x{p['kernel_end']:x}")

    print("② 规划组件")
    kc = load_kc()
    original = bytes(normalize_info(bytearray(kc[KC_KERNEL_OFF:])))
    native = bytes(strip_ctf(bytearray(io.open(KERNEL, "rb").read())))

    orig_kernel = tolerant_macho(original)
    # 组件块放在 kernel_end 之后
    block_start = align(p["kernel_end"])
    apple_pre = next(s for s in orig_kernel["segments"] if s["name"] == "__PRELINK_TEXT")
    slide = block_start - apple_pre["va"]
    slide = (slide + PAGE - 1) & ~(PAGE - 1)

    def noop(address, original_exports, native_by_name):
        return p["segs"][0]["vmaddr"]
    real = np.unique_kernel_binding
    np.unique_kernel_binding = noop
    probe = np.plan(native, original, ["com.apple.filesystems.apfs"], slide)
    np.unique_kernel_binding = real

    lo = min(e["va"] for e in probe["extents"])
    slide += block_start - lo
    slide = (slide + PAGE - 1) & ~(PAGE - 1)
    r = np.plan(native, original, ["com.apple.filesystems.apfs"], slide)
    print(f"   slide=0x{slide:x} 组件 {len(r['components'])} 绑定 {r['pointer_counts']}")

    print("③ 组装容器段（放在 kernel_end 之后）")
    by_container = {c: [] for c in COALESCED}
    for e in r["extents"]:
        c = next((k for k, v in COALESCED.items() if v == e["segment"]), None)
        if c:
            by_container[c].append(e)

    new_segs = []
    cursor = block_start
    for cname in ("__PRELINK_TEXT", "__PLK_TEXT_EXEC", "__PLK_DATA_CONST", "__PRELINK_DATA"):
        items = by_container.get(cname) or []
        if not items:
            continue
        size = align(max(i["va"] + i["size"] for i in items) - min(i["va"] for i in items))
        # 让段地址连着排（组件 VA 已由 slide 决定；这里只保证段之间不重叠）
        seg_va = max(cursor, min(i["va"] for i in items) & ~(PAGE - 1))
        vsize = align(max(i["va"] + i["size"] for i in items) - seg_va)
        buf = bytearray(vsize)
        for it in items:
            oseg = next((s for s in orig_kernel["segments"]
                         if s["va"] <= it["va"] - slide < s["va"] + s["size"]), None)
            if not oseg:
                continue
            off_in = oseg["fileoff"] + (it["va"] - slide) - oseg["va"]
            chunk = original[off_in:off_in + it["size"]]
            at = it["va"] - seg_va
            buf[at:at + len(chunk)] = chunk
        new_segs.append(dict(name=cname, vmaddr=seg_va, vmsize=vsize, data=bytes(buf)))
        cursor = align(seg_va + vsize)
        print(f"   {cname:<18} va=0x{seg_va:x} vsize=0x{vsize:x}")

    print("④ 组装 payload")
    pieces = []
    for s in p["segs"]:
        pieces.append((s["vmaddr"], s["vmsize"], bytes(base[s["off"]:s["off"] + s["size"]]), None))
    for s in new_segs:
        pieces.append((s["vmaddr"], s["vmsize"], s["data"], s["name"]))
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
    print(f"   kernel_end -> 0x{kernel_end:x}，{len(pieces)} 段，{len(out):,} 字节")

    print("⑤ 修改内核 Mach-O 里的 __PRELINK_* 段表")
    text_entry = table[0]      # __TEXT 是第一个段
    text_va, text_vs, text_off, text_size = text_entry
    text_data = bytearray(out[text_off:text_off + text_size])
    updates = {s["name"]: (s["vmaddr"], s["vmsize"]) for s in new_segs}
    n = patch_macho_segments(text_data, updates)
    out[text_off:text_off + text_size] = text_data
    print(f"   已更新 {n} 个段")
    for name, (va, vs) in updates.items():
        print(f"     {name:<18} va=0x{va:x} vsize=0x{vs:x}")

    print("⑥ 重绑指针")
    ranges = [(s["vmaddr"], s["vmaddr"] + s["vmsize"]) for s in new_segs]
    applied = 0
    for b in r["bindings"]:
        site = b["new_site"]
        for (lo2, hi2), s in zip(ranges, new_segs):
            if lo2 <= site < hi2:
                foff = None
                for va, vs, off, size in table:
                    if va == s["vmaddr"]:
                        foff = off + (site - va)
                        break
                if foff is not None and foff + 8 <= len(out):
                    struct.pack_into("<Q", out, foff, b["new_target"])
                    applied += 1
                break
    print(f"   已重绑 {applied} / {len(r['bindings'])}")

    io.open(OUT, "wb").write(bytes(out))
    print(f"\n✅ {OUT}（{len(out):,} 字节）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
