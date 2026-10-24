#!/usr/bin/env python3
"""payload 层预链接 v3：组件放进 [virt_base, __TEXT) 的 kext 区。

与 v2 的区别：
  · virt_base 保持不变（它是内核编译期常量的函数：__TEXT 所在 32MB 块基址）
  · 0030 补丁已把 __TEXT 抬到 0xfffffe0009f04000，virt_base 变成 0x8000000，
    kext 区从 16MB 扩到约 31MB，足够放 APFS 组件集
  · 容器段就地放在 slide 后的位置（不需要额外重排）
  · 修改 payload 里内核 Mach-O 的 __PRELINK_* 段表
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
ADT = r"E:\ios-on-fuxi\rom\xnu\fuxi.adt"
PAGE = 0x4000
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
    region_lo = p["virt_base"]
    print(f"   virt_base=0x{p['virt_base']:x}  __TEXT=0x{text_va:x}  "
          f"kext 区 {(text_va - region_lo) / 1048576:.1f} MB")

    print("② 规划组件")
    kc = load_kc()
    original = bytes(normalize_info(bytearray(kc[KC_KERNEL_OFF:])))
    native = bytes(strip_ctf(bytearray(io.open(KERNEL, "rb").read())))
    orig_kernel = tolerant_macho(original)
    apple_pre = next(s for s in orig_kernel["segments"] if s["name"] == "__PRELINK_TEXT")

    slide = region_lo - apple_pre["va"]
    slide = (slide + PAGE - 1) & ~(PAGE - 1)

    real = np.unique_kernel_binding
    np.unique_kernel_binding = lambda a, o, n: text_va
    probe = np.plan(native, original, ["com.apple.filesystems.apfs"], slide)
    np.unique_kernel_binding = real

    lo = min(e["va"] for e in probe["extents"])
    hi = max(e["va"] + e["size"] for e in probe["extents"])
    need = hi - lo
    room = text_va - region_lo
    print(f"   组件块 {need / 1048576:.1f} MB / 可用 {room / 1048576:.1f} MB")
    if need > room:
        print("   ✗ 放不下")
        return 1
    slide += (region_lo - lo)
    slide = (slide + PAGE - 1) & ~(PAGE - 1)
    r = np.plan(native, original, ["com.apple.filesystems.apfs"], slide)
    print(f"   slide=0x{slide:x} 组件 {len(r['components'])} 绑定 {r['pointer_counts']}")

    print("③ 容器段")
    by_container = {c: [] for c in COALESCED}
    for e in r["extents"]:
        c = next((k for k, v in COALESCED.items() if v == e["segment"]), None)
        if c:
            by_container[c].append(e)

    new_segs = []
    for cname, items in by_container.items():
        if not items:
            continue
        seg_va = min(i["va"] for i in items) & ~(PAGE - 1)
        end_va = max(i["va"] + i["size"] for i in items)
        vsize = align(end_va - seg_va)
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
        print(f"   {cname:<18} va=0x{seg_va:x} vsize=0x{vsize:x}")

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
    text_va2, text_vs, text_off, text_size = table[0]
    text_data = bytearray(out[text_off:text_off + text_size])
    updates = {s["name"]: (s["vmaddr"], s["vmsize"]) for s in new_segs}
    n = patch_macho_segments(text_data, updates)
    out[text_off:text_off + text_size] = text_data
    print(f"   更新 {n} 个段")

    print("⑥ 重绑")
    seg_by_va = {s["vmaddr"]: s for s in new_segs}
    applied = 0
    for b in r["bindings"]:
        site = b["new_site"]
        for s in new_segs:
            if s["vmaddr"] <= site < s["vmaddr"] + s["vmsize"]:
                off = next(o for va, vs, o, size in table if va == s["vmaddr"])
                foff = off + (site - s["vmaddr"])
                if foff + 8 <= len(out):
                    struct.pack_into("<Q", out, foff, b["new_target"])
                    applied += 1
                break
    print(f"   已重绑 {applied} / {len(r['bindings'])}")

    io.open(OUT, "wb").write(bytes(out))
    print(f"\n✅ {OUT}（{len(out):,} 字节）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
