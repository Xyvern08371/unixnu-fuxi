#!/usr/bin/env python3
"""在 payload 层做预链接：把 Apple kernelcache 的组件注入我们内核的 payload。

为什么在 payload 层：
  我们的 mkpayload_fuxi 已经把内核的 chained fixup 全部重写成立即数（平铺镜像），
  若在原始 Mach-O 上改指针，随后打包会把它覆盖掉。所以在"已重定位的 payload"上
  追加组件段并重绑指针，产物直接给 shim 平铺拷贝。

流程：
  1. mkpayload_fuxi 生成基础 payload（已重定位）
  2. plan() 规划组件（选择、段范围、绑定）
  3. 选 slide，让组件落在 __PRELINK_TEXT 预留区（内核 __TEXT 之下 48MB）
  4. 把 4 个容器段作为新段加入 payload，并相应下调 virt_base
  5. 按绑定表在 payload 数据里重绑指针
  6. 输出新 payload + 段表信息
"""

import io
import struct
import sys

sys.path.insert(0, r"E:\ios-on-fuxi\tools")
sys.path.insert(0, r"E:\download\UniXNU\kits\NativePrelink")

import mkpayload_fuxi as mp
from prelink_try2 import load_kc, normalize_info, tolerant_macho, KC_KERNEL_OFF

KERNEL = r"E:\download\xnu-kernel-22\out\kernel.development.fuxi"
ADT = r"E:\ios-on-fuxi\rom\xnu\fuxi.adt"
OUT_PAYLOAD = r"E:\download\payload-prelinked.bin"
PAGE = 0x4000
L2 = 0x2000000
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


def main() -> int:
    import native_prelink as np
    np.macho = tolerant_macho

    print("① 生成基础 payload（已重定位）")
    base, info = mp.build(KERNEL, ADT, "debug=0xc serial=3 cpus=1 keepsyms=1 -v kdp_match_name=none")
    p = parse_payload(base)
    print(f"   {len(base):,} 字节，{len(p['segs'])} 段，virt_base=0x{p['virt_base']:x}")

    print("② 规划组件")
    kc = load_kc()
    original = bytes(normalize_info(bytearray(kc[KC_KERNEL_OFF:])))
    text_va = p["segs"][0]["vmaddr"]          # __TEXT
    # 预留区起点：__TEXT 之下 48MB（XNU 的 kexts 区）
    region_lo = text_va - 0x3000000

    native = bytearray(io.open(KERNEL, "rb").read())
    # 供 plan 使用：去掉 __CTF（与打包器一致的行为）
    from prelink_try2 import strip_ctf
    native = bytes(strip_ctf(native))

    orig_kernel = tolerant_macho(original)
    apple_pre = next(s for s in orig_kernel["segments"] if s["name"] == "__PRELINK_TEXT")
    slide0 = region_lo - apple_pre["va"]
    slide0 = (slide0 + PAGE - 1) & ~(PAGE - 1)

    # 第一遍：拿范围
    def noop(address, original_exports, native_by_name):
        return text_va
    real = np.unique_kernel_binding
    np.unique_kernel_binding = noop
    probe = np.plan(native, original, ["com.apple.filesystems.apfs"], slide0)
    np.unique_kernel_binding = real

    lo = min(e["va"] for e in probe["extents"])
    hi = max(e["va"] + e["size"] for e in probe["extents"])
    print(f"   组件块 0x{lo:x} .. 0x{hi:x}（{(hi - lo) / 1048576:.1f} MB）")
    if hi > text_va:
        print("   ✗ 组件块越过内核 __TEXT")
        return 1
    # 精确对齐：让块起点落在 region_lo
    slide = slide0 + (region_lo - lo)
    slide = (slide + PAGE - 1) & ~(PAGE - 1)
    r = np.plan(native, original, ["com.apple.filesystems.apfs"], slide)
    print(f"   slide=0x{slide:x} 组件 {len(r['components'])} 绑定 {r['pointer_counts']}")

    print("③ 组装容器段")
    by_container = {c: [] for c in COALESCED}
    for e in r["extents"]:
        c = next((k for k, v in COALESCED.items() if v == e["segment"]), None)
        if c:
            by_container[c].append(e)

    new_segs = []
    for cname, items in by_container.items():
        if not items:
            continue
        base_va = min(i["va"] for i in items) & ~(PAGE - 1)
        end_va = max(i["va"] + i["size"] for i in items)
        vsize = align(end_va - base_va)
        buf = bytearray(vsize)
        for it in items:
            oseg = next((s for s in orig_kernel["segments"]
                         if s["va"] <= it["va"] - slide < s["va"] + s["size"]), None)
            if not oseg:
                continue
            off_in = oseg["fileoff"] + (it["va"] - slide) - oseg["va"]
            chunk = original[off_in:off_in + it["size"]]
            at = it["va"] - base_va
            buf[at:at + len(chunk)] = chunk
        new_segs.append(dict(name=cname, vmaddr=base_va, vmsize=vsize, data=bytes(buf)))
        print(f"   {cname:<18} va=0x{base_va:x} vsize=0x{vsize:x}")

    print("④ 写 payload")
    virt_base = min([p["segs"][0]["vmaddr"]] + [s["vmaddr"] for s in new_segs]) & ~(L2 - 1)
    pieces = []
    for s in p["segs"]:
        pieces.append((s["vmaddr"], s["vmsize"], bytes(base[s["off"]:s["off"] + s["size"]])))
    for s in new_segs:
        pieces.append((s["vmaddr"], s["vmsize"], s["data"]))
    pieces.sort(key=lambda t: t[0])

    kernel_end = align(max(va + vs for va, vs, _ in pieces))
    hdr = 0x2A8 + 32 * len(pieces)
    out = bytearray(hdr)
    table = []
    for va, vs, data in pieces:
        off = len(out)
        out += data
        out += b"\0" * (-len(out) & 0xF)
        table.append((va, vs, off, len(data)))

    adt_off = len(out)
    out += base[p["adt_off"]:p["adt_off"] + p["adt_size"]]
    out += b"\0" * (-len(out) & 0xF)

    struct.pack_into("<8sII", out, 0, b"FUXIXNU", 1, len(pieces))
    struct.pack_into("<7Q", out, 0x10, virt_base, p["entry"], adt_off, p["adt_size"],
                     kernel_end, p["phys_base"], p["mem_size"])
    cl = p["cmdline"].encode()[:607]
    out[0x48:0x48 + len(cl)] = cl
    for i, t in enumerate(table):
        struct.pack_into("<4Q", out, 0x2A8 + 32 * i, *t)

    print(f"   virt_base 0x{p['virt_base']:x} -> 0x{virt_base:x}")
    print(f"   kernel_end 0x{p['kernel_end']:x} -> 0x{kernel_end:x}")
    print(f"   {len(pieces)} 段，{len(out):,} 字节")

    print("⑤ 重绑指针")
    # 新段 VA 范围
    ranges = [(s["vmaddr"], s["vmaddr"] + s["vmsize"], s) for s in new_segs]
    applied = missing_site = 0
    for b in r["bindings"]:
        site = b["new_site"]
        for lo2, hi2, s in ranges:
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
        else:
            missing_site += 1
    print(f"   已重绑 {applied} / {len(r['bindings'])}（site 不在组件段内 {missing_site}）")

    io.open(OUT_PAYLOAD, "wb").write(bytes(out))
    print(f"\n✅ {OUT_PAYLOAD}（{len(out):,} 字节）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
