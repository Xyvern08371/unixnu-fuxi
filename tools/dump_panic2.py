#!/usr/bin/env python3
"""从 panic 之后的内存里读出 panic 字符串。

用法: dump_panic2.py <payload> <kernel>
自动从内核符号表解析 _debugger_panic_str / _panic_info 等地址，
按 payload 的 virt_base/phys_base 换算物理地址后 dump。
"""

import os
import struct
import subprocess
import sys
import time

sys.path.insert(0, r"E:\ios-on-fuxi\tools")
import qemu_fuxi as qf
from qemu_shim import Qmp

SYMS = ["_debugger_panic_str", "_debugger_panic_data", "_panic_info",
        "_debug_buf_base", "_debug_buf_ptr", "_debug_buf_size", "_panic_data_buffers"]


def load_syms(path):
    d = open(path, "rb").read()
    ncmds, = struct.unpack_from("<I", d, 16)
    p, symtab = 32, None
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", d, p)
        if cmd == 0x2:
            symtab = struct.unpack_from("<4I", d, p + 8)
        p += size
    so, ns, sto, ss = symtab
    out = {}
    for i in range(ns):
        o = so + i * 16
        strx, ntype, sect, desc, val = struct.unpack_from("<IBBHQ", d, o)
        if val == 0:
            continue
        e = d.index(b"\0", sto + strx)
        out[d[sto + strx:e].decode("latin1", "replace")] = val
    return out


def main() -> int:
    payload_path = sys.argv[1]
    kernel_path = sys.argv[2]
    payload = open(payload_path, "rb").read()
    syms = load_syms(kernel_path)

    virt_base, = struct.unpack_from("<Q", payload, 0x10)
    phys_base, = struct.unpack_from("<Q", payload, 0x38)

    out = r"E:\qemurun"
    os.makedirs(out, exist_ok=True)
    phys, img, ba_pa, entry_pa = qf.build_image(payload)
    open(os.path.join(out, "ram.bin"), "wb").write(img)
    open(os.path.join(out, "stub.bin"), "wb").write(qf.build_stub(ba_pa, entry_pa))
    mem_size = struct.unpack_from("<Q", payload, 0x40)[0]
    ram_gib = max(4, -(-(phys + mem_size - 0x40000000) // (1 << 30)))

    cmd = [
        qf.QEMU, "-M", "virt,gic-version=3", "-cpu", "cortex-a76", "-smp", "1",
        "-m", f"{ram_gib}G", "-nographic", "-no-reboot",
        "-qmp", "tcp:127.0.0.1:4457,server,nowait",
        "-device", f"loader,file={out}/ram.bin,addr={phys:#x},force-raw=on",
        "-device", f"loader,file={out}/stub.bin,addr={qf.STUB_PA:#x},force-raw=on",
        "-device", f"loader,addr={qf.STUB_PA:#x},cpu-num=0",
    ]
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.PIPE)
    time.sleep(2)
    q = Qmp(4457)
    time.sleep(9)
    q.cmd("stop")

    def rd(va, size):
        f = os.path.join(out, "t.bin")
        q.cmd("pmemsave", val=phys + (va - virt_base), size=size, filename=f)
        return open(f, "rb").read()

    def rdq(va):
        return struct.unpack("<Q", rd(va, 8))[0]

    print(f"  virt_base=0x{virt_base:x} phys_base=0x{phys:x}")
    for name in SYMS:
        va = syms.get(name)
        if not va:
            print(f"  {name}: 无符号")
            continue
        try:
            raw = rd(va, 64)
        except Exception as e:
            print(f"  {name}: 读失败 {e}")
            continue
        txt = raw.split(b"\0")[0]
        printable = txt and all(32 <= c < 127 for c in txt)
        print(f"  {name} @0x{va:x}: ", end="")
        if printable:
            print(txt.decode("latin1"))
        else:
            ptr = struct.unpack_from("<Q", raw, 0)[0]
            print(f"非字符串，首 qword=0x{ptr:x}")
            if virt_base <= ptr < virt_base + 0x10000000:
                s = rd(ptr, 256).split(b"\0")[0]
                if s and all(32 <= c < 127 or c in (9, 10) for c in s):
                    print(f"      -> {s.decode('latin1')[:200]}")

    p.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
