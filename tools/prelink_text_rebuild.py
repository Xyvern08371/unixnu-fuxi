#!/usr/bin/env python3
"""按 XNU 的模型重建 __PRELINK_TEXT 容器。

XNU 的 kalloc_type_view_parse（KCGEN 分支）这样走：
    cur = __PRELINK_TEXT.__text.addr
    while cur < end:
        读 kext Mach-O 头（magic 必须是 MH_MAGIC_64，或全 0 表示结束）
        kext_text_sz = 该 kext 的 __TEXT segment filesize（没有则 sizeofcmds）
        cur += align(kext_text_sz, 0x4000)

所以在 __PRELINK_TEXT 里每个 kext 只放 Mach-O 头（32 + sizeofcmds），
后面按 __TEXT filesize 补 0。这里按这个规则重建，并把段/节地址重映射。
"""

import struct

MH_MAGIC_64 = 0xFEEDFACF
LC_SEGMENT_64 = 0x19
KEXT_ALIGN = 0x4000


def align(x, a=KEXT_ALIGN):
    return (x + a - 1) & ~(a - 1)


def _parse_header(buf, cur):
    """返回 (header_size, text_filesize, segments) 或 None"""
    if cur + 32 > len(buf):
        return None
    magic, = struct.unpack_from("<I", buf, cur)
    if magic != MH_MAGIC_64:
        return None
    ncmds, sizeofcmds = struct.unpack_from("<II", buf, cur + 16)
    header_size = 32 + sizeofcmds
    if cur + header_size > len(buf):
        return None
    text_sz = 0
    segs = []
    lc = cur + 32
    for _ in range(ncmds):
        if lc + 8 > len(buf):
            break
        cmd, cmdsize = struct.unpack_from("<II", buf, lc)
        if cmdsize < 8:
            break
        if cmd == LC_SEGMENT_64 and cmdsize >= 72:
            name = bytes(buf[lc + 8:lc + 24]).split(b"\0")[0].decode("latin1")
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<4Q", buf, lc + 24)
            nsects, = struct.unpack_from("<I", buf, lc + 64)
            secs = []
            for si in range(nsects):
                sp = lc + 72 + si * 80
                if sp + 48 > len(buf):
                    break
                saddr, = struct.unpack_from("<Q", buf, sp + 32)
                secs.append((sp, saddr))
            segs.append((lc, name, vmaddr, filesize, secs))
            if name == "__TEXT" and filesize:
                text_sz = filesize
        lc += cmdsize
    return header_size, text_sz, segs


def rebuild(orig_buf, orig_va, out_size, mapping, verbose=True):
    """orig_buf: 原始 __PRELINK_TEXT 数据；orig_va: 其 VA；out_size: 目标大小"""
    out = bytearray(out_size)

    def map_va(old):
        for lo, hi, delta in mapping:
            if lo <= old < hi:
                return old + delta
        return None

    src = 0
    dst = 0
    n = 0
    while src < len(orig_buf) and dst + 32 <= out_size:
        parsed = _parse_header(orig_buf, src)
        if not parsed:
            break
        header_size, text_sz, segs = parsed
        stride_src = align(text_sz or header_size)
        stride_dst = align(text_sz or header_size)

        blob = bytearray(orig_buf[src:src + header_size])
        fixed = 0
        for lc, name, vmaddr, filesize, secs in segs:
            new = map_va(vmaddr)
            if new is not None:
                struct.pack_into("<Q", blob, lc + 24, new)
                fixed += 1
            for sp, saddr in secs:
                snew = map_va(saddr)
                if snew is not None:
                    struct.pack_into("<Q", blob, sp + 32, snew)
        out[dst:dst + header_size] = blob
        if verbose:
            ident = ""
            for lc, name, vmaddr, filesize, secs in segs:
                pass
            print(f"     kext#{n} src=0x{src:x} dst=0x{dst:x} hdr=0x{header_size:x} "
                  f"text=0x{text_sz:x} 段地址改写 {fixed}")
        src += stride_src
        dst += stride_dst
        n += 1
    if verbose:
        print(f"   重建 {n} 个 kext，容器 0x{dst:x} / 0x{out_size:x}，其余清零")
    return bytes(out)
