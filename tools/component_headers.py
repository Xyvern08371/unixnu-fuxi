#!/usr/bin/env python3
"""把组件 Mach-O 头里的段/节地址从 Apple 布局改写到我们重排后的地址。

XNU 的 kalloc_type_view_parse（KCGEN 分支）会遍历 __PRELINK_TEXT 里的每个 kext
Mach-O，读它的 __DATA_CONST.__kalloc_type 节地址去解析类型视图；地址留在 Apple
布局就会访问未映射地址 → 缺页 → 早期 panic。
"""

import struct

MH_MAGIC_64 = 0xFEEDFACF
LC_SEGMENT_64 = 0x19
KEXT_ALIGN = 0x4000


def align(x, a=KEXT_ALIGN):
    return (x + a - 1) & ~(a - 1)


def remap(buf: bytearray, mapping, verbose=False) -> int:
    """mapping: [(old_lo, old_hi, delta)]。返回改写的段数。"""

    def map_va(old):
        for lo, hi, delta in mapping:
            if lo <= old < hi:
                return old + delta
        return None

    cur = 0
    last_end = 0
    fixed_segs = 0
    n_machos = 0
    while cur + 32 <= len(buf):
        magic, = struct.unpack_from("<I", buf, cur)
        if magic == 0:
            break
        if magic != MH_MAGIC_64:
            if verbose:
                print(f"   walk 停在 0x{cur:x}（magic=0x{magic:x}）")
            break
        ncmds, = struct.unpack_from("<I", buf, cur + 16)
        sizeofcmds, = struct.unpack_from("<I", buf, cur + 20)
        n_machos += 1
        text_sz = 0
        split = False
        lc = cur + 32
        for _ in range(ncmds):
            if lc + 8 > len(buf):
                break
            cmd, cmdsize = struct.unpack_from("<II", buf, lc)
            if cmdsize < 8:
                break
            if cmd == 0x1E:          # LC_SEGMENT_SPLIT_INFO
                split = True
            elif cmd == LC_SEGMENT_64 and cmdsize >= 72:
                name = bytes(buf[lc + 8:lc + 24]).split(b"\0")[0].decode("latin1")
                vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<4Q", buf, lc + 24)
                new = map_va(vmaddr)
                if new is not None and new != vmaddr:
                    struct.pack_into("<Q", buf, lc + 24, new)
                    fixed_segs += 1
                if name == "__TEXT" and filesize:
                    text_sz = filesize
                nsects, = struct.unpack_from("<I", buf, lc + 64)
                for si in range(nsects):
                    sp = lc + 72 + si * 80
                    if sp + 48 > len(buf):
                        break
                    saddr, = struct.unpack_from("<Q", buf, sp + 32)
                    snew = map_va(saddr)
                    if snew is not None and snew != saddr:
                        struct.pack_into("<Q", buf, sp + 32, snew)
                if name == "__DATA_CONST":
                    pass
            lc += cmdsize
        if verbose:
            print(f"     cur=0x{cur:x} ncmds={ncmds} sizeofcmds=0x{sizeofcmds:x} text_filesize=0x{text_sz:x} split={split}")
        if not text_sz:
            text_sz = sizeofcmds
        elif not split:
            # XNU 会对非 split 的 kext panic；我们的组件是 Apple 的 split 布局
            pass
        stride = align(text_sz)
        hdr_end = cur + 32 + sizeofcmds
        if hdr_end < cur + stride:
            buf[hdr_end:cur + stride] = b"\0" * (cur + stride - hdr_end)
        cur += stride
        last_end = cur
    # XNU 的遍历在 magic==0 处要求 [cur, end) 全为 0，否则断言失败。
    # 从最后一个 kext 的 stride 边界开始清零，确保尾部干净。
    import os as _os
    if _os.environ.get("ONLY_FIRST"):
        # 只保留第一个 kext 头，其余清零（绕开遍历断言，用于验证到 kdp_core）
        first_hdr_end = 0
        magic, = struct.unpack_from("<I", buf, 0)
        if magic == MH_MAGIC_64:
            sizeofcmds, = struct.unpack_from("<I", buf, 20)
            first_hdr_end = 32 + sizeofcmds
        buf[first_hdr_end:] = b"\0" * (len(buf) - first_hdr_end)
        if verbose:
            print(f"   ONLY_FIRST：只保留 0x{first_hdr_end:x} 字节头部")
        return fixed_segs
    tail = min(last_end, len(buf))
    if tail < len(buf):
        buf[tail:] = b"\0" * (len(buf) - tail)
    if verbose:
        print(f"   处理 {n_machos} 个组件 Mach-O，改写 {fixed_segs} 个段地址，尾部清零 0x{cur:x}..0x{len(buf):x}")
    return fixed_segs
