#!/usr/bin/env python3
"""解析 Mach-O 64 位内核镜像，输出引导器需要的加载信息。

用法:
    python3 tools/macho.py <kernel 文件>

输出:
    - CPU / 文件类型 / 入口点（LC_MAIN 或 _start 符号）
    - 每个 LC_SEGMENT_64 的 segname / vmaddr / vmsize / fileoff / filesize
    - 由这些算出的"加载计划"：目标物理地址、需要拷贝的范围
"""

import struct
import sys

MH_MAGIC_64 = 0xFEEDFACF
LC_SEGMENT_64 = 0x19
LC_MAIN = 0x80000028

CPU_NAMES = {0x0100000C: "ARM64", 0x0100000C | 0x01000000: "ARM64E"}
FILE_TYPES = {2: "MH_EXECUTE", 11: "MH_KEXT_BUNDLE", 6: "MH_DYLIB", 8: "MH_BUNDLE"}


def parse(path):
    data = open(path, "rb").read()
    if len(data) < 32:
        print("文件太小，不是 Mach-O")
        return

    magic, cpu, subtype, ftype, ncmds, sizeofcmds, flags, _res = struct.unpack_from("<IiiIIIII", data, 0)
    if magic != MH_MAGIC_64:
        print("不是 Mach-O 64 位小端（magic=0x%08X）" % magic)
        print("文件头前 16 字节:", data[:16].hex())
        return

    print("=== Mach-O 头 ===")
    print("  magic      : 0x%08X" % magic)
    print("  cpu        : 0x%08X (%s)" % (cpu, CPU_NAMES.get(cpu, "未知")))
    print("  subtype    : 0x%08X" % (subtype & 0xFFFFFFFF))
    print("  filetype   : %d (%s)" % (ftype, FILE_TYPES.get(ftype, "?")))
    print("  ncmds      : %d" % ncmds)
    print("  sizeofcmds : %d" % sizeofcmds)
    print("  flags      : 0x%08X" % flags)
    print("  文件大小   : %d 字节" % len(data))

    off = 32
    segs = []
    entry_off = None
    print("\n=== 段（LC_SEGMENT_64）===")
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from("<II", data, off)
        if cmd == LC_SEGMENT_64:
            segname = data[off + 8:off + 24].split(b"\0")[0].decode("ascii", "replace")
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<QQQQ", data, off + 24)
            maxprot, initprot, nsects, sflags = struct.unpack_from("<iiII", data, off + 56)
            segs.append({
                "name": segname, "vmaddr": vmaddr, "vmsize": vmsize,
                "fileoff": fileoff, "filesize": filesize,
                "initprot": initprot, "nsects": nsects,
            })
            print("  %-16s vmaddr=0x%016x vmsize=0x%010x fileoff=0x%08x filesize=0x%010x prot=%d"
                  % (segname, vmaddr, vmsize, fileoff, filesize, initprot))
        elif cmd == LC_MAIN:
            entry_off, = struct.unpack_from("<Q", data, off + 8)
            print("\n  LC_MAIN entryoff = 0x%x" % entry_off)
        off += cmdsize

    if not segs:
        print("没有找到任何段")
        return

    # 入口：优先 LC_MAIN（相对文件偏移），否则用第一个可执行段的 vmaddr
    print("\n=== 加载计划 ===")
    first = segs[0]
    base_va = first["vmaddr"]
    print("  链接基址（第一个段的 vmaddr）: 0x%016x" % base_va)

    dst = 0x80000000  # 我们打算放在 DRAM 起点附近
    for s in segs:
        delta = s["vmaddr"] - base_va
        print("  %-16s -> 物理 0x%09x  (拷贝 %d 字节, 零填 %d 字节)"
              % (s["name"], dst + delta, s["filesize"], s["vmsize"] - s["filesize"]))

    if entry_off is not None:
        # entryoff 是相对 __TEXT 文件起点的偏移；换算成虚拟地址
        text = next((s for s in segs if s["name"] == "__TEXT"), first)
        entry_va = text["vmaddr"] + entry_off
        print("  入口（由 LC_MAIN 换算）: 虚拟 0x%016x -> 物理 0x%09x"
              % (entry_va, dst + (entry_va - base_va)))
    else:
        print("  入口: 没有 LC_MAIN，需要从符号表找 _start")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    parse(sys.argv[1])
