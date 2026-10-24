#!/usr/bin/env python3
"""把 shim 的 ELF 转成平铺 binary（等价于 objcopy -O binary）。

shim 链接时是 "place anywhere"（ABL 直接按 PA 加载），所以把每个 PT_LOAD
按 p_paddr 顺序拼起来即可。
"""

import struct
import sys


def elf_to_bin(path, out_path):
    d = open(path, "rb").read()
    assert d[:4] == b"\x7fELF", "不是 ELF"
    is64 = d[4] == 2
    le = d[5] == 1
    assert is64 and le, "只支持 ELF64 LE"
    e_phoff, = struct.unpack_from("<Q", d, 0x20)
    e_phentsize, e_phnum = struct.unpack_from("<HH", d, 0x36)

    loads = []
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        p_type, p_flags = struct.unpack_from("<II", d, off)
        if p_type != 1:          # PT_LOAD
            continue
        p_offset, p_vaddr, p_paddr, p_filesz, p_memsz = struct.unpack_from("<QQQQQ", d, off + 8)
        loads.append(dict(offset=p_offset, vaddr=p_vaddr, paddr=p_paddr,
                          filesz=p_filesz, memsz=p_memsz))

    loads.sort(key=lambda s: s["paddr"])
    base = loads[0]["paddr"]
    end = max(s["paddr"] + s["memsz"] for s in loads)
    out = bytearray(end - base)
    for s in loads:
        at = s["paddr"] - base
        out[at:at + s["filesz"]] = d[s["offset"]:s["offset"] + s["filesz"]]
    open(out_path, "wb").write(out)
    print(f"  ELF: {len(d):,} 字节, {len(loads)} 个 PT_LOAD, base=0x{base:x} -> "
          f"flat {len(out):,} 字节")
    return base


if __name__ == "__main__":
    elf_to_bin(sys.argv[1], sys.argv[2])
