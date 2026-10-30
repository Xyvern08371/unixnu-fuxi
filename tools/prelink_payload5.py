#!/usr/bin/env python3
"""payload 层预链接 v5：组件 + 真实 __PRELINK_INFO。

在 v4 的基础上补上 kext 清单：XNU 加载预链接 kext 需要每个条目里的
  _PrelinkExecutableLoadAddr / _PrelinkExecutableSourceAddr /
  _PrelinkExecutableSize / _PrelinkKmodInfo
这些地址都要换成我们重排后的新地址。
"""

import io
import struct
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, r"E:\ios-on-fuxi\tools")
sys.path.insert(0, r"E:\download\UniXNU\kits\NativePrelink")

import mkpayload_fuxi as mp
from prelink_try2 import load_kc, normalize_info, tolerant_macho, strip_ctf, KC_KERNEL_OFF
import component_headers, prelink_text_rebuild

KERNEL = sys.argv[1] if len(sys.argv) > 1 else r"E:\download\xnu-kernel-23\out\kernel.development.fuxi"
ADT = sys.argv[2] if len(sys.argv) > 2 else r"E:\ios-on-fuxi\rom\xnu\fuxi.adt"
OUT = sys.argv[3] if len(sys.argv) > 3 else r"E:\download\payload-prelinked.bin"
PAGE = 0x4000
CONTAINER_ORDER = ["__PRELINK_TEXT", "__PLK_TEXT_EXEC", "__PLK_DATA_CONST", "__PRELINK_DATA"]
COALESCED = {"__PRELINK_TEXT": "__TEXT", "__PLK_TEXT_EXEC": "__TEXT_EXEC",
             "__PLK_DATA_CONST": "__DATA_CONST", "__PRELINK_DATA": "__DATA"}
COPY_KEYS = ("CFBundleIdentifier", "OSBundleLibraries", "CFBundleVersion",
             "OSBundleCompatibleVersion", "OSBundleRequired", "OSKernelResource",
             "_PrelinkExecutableSize", "_PrelinkExecutableLoadAddr",
             "_PrelinkExecutableSourceAddr", "_PrelinkKmodInfo")


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
    assert magic == 0xFEEDFACF
    ncmds, = struct.unpack_from("<I", text_data, 16)
    p, done = 32, 0
    for _ in range(ncmds):
        cmd, length = struct.unpack_from("<II", text_data, p)
        if cmd == 0x19 and length >= 72:
            name = bytes(text_data[p + 8:p + 24]).split(b"\0")[0].decode()
            if name in updates:
                va, vsize = updates[name]
                struct.pack_into("<Q", text_data, p + 24, va)
                struct.pack_into("<Q", text_data, p + 32, vsize)
                # 段内各 section 的 addr/size 也要跟着改：
                # 内核判断"是否预链接"用的是 __PRELINK_INFO/__info 的 section size
                nsects, = struct.unpack_from("<I", text_data, p + 64)
                for si in range(nsects):
                    sp = p + 72 + si * 80
                    struct.pack_into("<Q", text_data, sp + 32, va)      # addr
                    struct.pack_into("<Q", text_data, sp + 40, vsize)   # size
                    struct.pack_into("<I", text_data, sp + 48, 0)       # offset
                done += 1
        p += length
    return done


def build_info_xml(entries_dict, selected, mapping):
    """从原始 prelink info 里取选中组件，重写地址字段，输出 Apple 风格的 XML"""

    def map_va(old):
        for lo, hi, delta in mapping:
            if lo <= old < hi:
                return old + delta
        return None

    root = ET.Element("dict")
    ET.SubElement(root, "key").text = "_PrelinkInfoDictionary"
    arr = ET.SubElement(root, "array")

    ADDR_KEYS = ("_PrelinkExecutableLoadAddr", "_PrelinkExecutableSourceAddr",
                 "_PrelinkKmodInfo")
    kept = 0
    for ident in selected:
        src = entries_dict.get(ident)
        if not src:
            continue
        d = ET.SubElement(arr, "dict")
        for key in COPY_KEYS:
            if key not in src:
                continue
            val = src[key]
            ET.SubElement(d, "key").text = key
            if isinstance(val, dict):
                sub = ET.SubElement(d, "dict")
                for k2, v2 in val.items():
                    ET.SubElement(sub, "key").text = k2
                    ET.SubElement(sub, "string").text = str(v2)
            elif isinstance(val, bool):
                ET.SubElement(d, "true" if val else "false")
            elif isinstance(val, int):
                if key in ADDR_KEYS:
                    mapped = map_va(val)
                    if mapped is not None:
                        val = mapped
                el = ET.SubElement(d, "integer", {"size": "64"})
                el.text = hex(val)
            else:
                ET.SubElement(d, "string").text = str(val)
        kept += 1
    body = ET.tostring(root, encoding="utf-8")
    return body, kept


def main() -> int:
    import native_prelink as np
    np.macho = tolerant_macho

    print("① 基础 payload")
    base, _ = mp.build(KERNEL, ADT, "debug=0xc serial=3 cpus=1 keepsyms=1 -v kdp_match_name=none")
    p = parse_payload(base)
    text_va = p["segs"][0]["vmaddr"]

    # 关键：预链接内核的 virt_base 必须取"最低段的 VA"（UniXNU 的 DarwinBoot 就是这样：
    # pa = window_base + (entry - Kernel.Base)）。内核为 kexts 预留的 48MB 区
    # 就在 __PRELINK_TEXT 占位地址到 __TEXT 之间，只有让 virt_base 落到那里，
    # shim 才会把组件拷贝进去。
    knative = tolerant_macho(io.open(KERNEL, "rb").read())
    pre_placeholder = next(s for s in knative["segments"] if s["name"] == "__PRELINK_TEXT")["va"]
    import os as _os
    region_lo = pre_placeholder
    if _os.environ.get("COMPONENTS_TOP"):
        # 把组件贴到 __TEXT 下方（保持 segLOWESTTEXT 仍是 __TEXT 附近的量级）
        region_lo = text_va - 0x400000
    out_virt_base = region_lo & ~0x1FFFFFF        # 32MB 对齐
    print(f"   组件区从 0x{region_lo:x} 到 __TEXT 0x{text_va:x}（{(text_va - region_lo)/1048576:.1f} MB），virt_base 输出为 0x{out_virt_base:x}")

    print("② 规划")
    kc = load_kc()
    original = bytes(normalize_info(bytearray(kc[KC_KERNEL_OFF:])))
    native = bytes(strip_ctf(bytearray(io.open(KERNEL, "rb").read())))
    orig_kernel = tolerant_macho(original)
    r = np.plan(native, original, ["com.apple.filesystems.apfs"], 0)
    print(f"   组件 {len(r['components'])} 绑定 {r['pointer_counts']}")

    # 原始 prelink info（已归一化为合法 XML）
    info_seg = next(s for s in orig_kernel["segments"] if s["name"] == "__PRELINK_INFO")
    info_blob = original[info_seg["fileoff"]:info_seg["fileoff"] + info_seg["size"]]
    meta = np.unserialize_xml(info_blob)
    entries = {e["CFBundleIdentifier"]: e for e in meta["_PrelinkInfoDictionary"]}
    print(f"   原始条目 {len(entries)}")

    print("③ 紧凑打包")
    by_container = {c: [] for c in CONTAINER_ORDER}
    for e in r["extents"]:
        c = next((k for k, v in COALESCED.items() if v == e["segment"]), None)
        if c:
            by_container[c].append(e)

    new_segs, mapping = [], []
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
            mapping.append((it["va"], it["va"] + it["size"], seg_va + at - it["va"]))
        vsize = align(len(buf))
        buf += b"\0" * (vsize - len(buf))
        new_segs.append(dict(name=cname, vmaddr=seg_va, vmsize=vsize, data=bytes(buf)))
        cursor = align(seg_va + vsize)
        print(f"   {cname:<18} va=0x{seg_va:x} vsize=0x{vsize:x}")

    print("③b 重写组件 Mach-O 段/节地址 + 每个 kext 头部之后清零（符合 XNU 遍历模型）")
    for s in new_segs:
        if s["name"] == "__PRELINK_TEXT":
            buf = bytearray(s["data"])
            component_headers.remap(buf, mapping, verbose=True)
            s["data"] = bytes(buf)
            break

    print("④ 生成 __PRELINK_INFO")
    xml, kept = build_info_xml(entries, r["components"], mapping)
    info_va = cursor
    info_vsize = align(len(xml))
    new_segs.append(dict(name="__PRELINK_INFO", vmaddr=info_va, vmsize=info_vsize,
                         data=xml + b"\0" * (info_vsize - len(xml))))
    cursor = align(info_va + info_vsize)
    print(f"   条目 {kept}，XML {len(xml):,} 字节 @va 0x{info_va:x}")

    if cursor > text_va:
        print(f"   ✗ 超出 kext 区（0x{cursor:x} > 0x{text_va:x}）")
        return 1

    print("⑤ 组装 payload")
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
    struct.pack_into("<7Q", out, 0x10, out_virt_base, p["entry"], adt_off, p["adt_size"],
                     kernel_end, p["phys_base"], p["mem_size"])
    cl = p["cmdline"].encode()[:607]
    out[0x48:0x48 + len(cl)] = cl
    for i, t in enumerate(table):
        struct.pack_into("<4Q", out, 0x2A8 + 32 * i, *t)
    print(f"   kernel_end=0x{kernel_end:x} {len(pieces)} 段 {len(out):,} 字节")

    print("⑥ 改内核 Mach-O 段表")
    toff = next(off for va, vs, off, size in table if va == text_va)
    tsize = next(size for va, vs, off, size in table if va == text_va)
    text_data = bytearray(out[toff:toff + tsize])
    updates = {s["name"]: (s["vmaddr"], s["vmsize"]) for s in new_segs}
    n = patch_macho_segments(text_data, updates)
    out[toff:toff + tsize] = text_data
    print(f"   更新 {n} 个段")

    print("⑦ 重绑")
    applied = skipped = 0
    for b in r["bindings"]:
        new_site = None
        for lo, hi, delta in mapping:
            if lo <= b["site"] < hi:
                new_site = b["site"] + delta
                break
        if new_site is None:
            skipped += 1
            continue
        target = b["new_target"]
        if b["kind"] == "component":
            for lo, hi, delta in mapping:
                if lo <= target < hi:
                    target = target + delta
                    break
            else:
                skipped += 1
                continue
        seg = next((s for s in new_segs if s["vmaddr"] <= new_site < s["vmaddr"] + s["vmsize"]), None)
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
