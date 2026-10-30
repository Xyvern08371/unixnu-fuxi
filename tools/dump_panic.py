#!/usr/bin/env python3
"""panic 之后从内存里把 panic 字符串 dump 出来（绕过控制台）。"""

import os
import struct
import subprocess
import sys
import time

sys.path.insert(0, r"E:\ios-on-fuxi\tools")
import qemu_fuxi as qf
from qemu_shim import Qmp

PAYLOAD = sys.argv[1] if len(sys.argv) > 1 else r"E:\download\payload-prelinked.bin"
OUT = r"E:\qemurun"

# _debugger_panic_str 的 VA（kernel 22）
PANIC_STR_VA = 0xFFFFFE0007AEF4D8
PANIC_DATA_VA = 0xFFFFFE0007AEF4E8


def main() -> int:
    payload = open(PAYLOAD, "rb").read()
    os.makedirs(OUT, exist_ok=True)
    phys_base, img, ba_pa, entry_pa = qf.build_image(payload)
    virt_base, = struct.unpack_from("<Q", payload, 0x10)

    open(os.path.join(OUT, "ram.bin"), "wb").write(img)
    open(os.path.join(OUT, "stub.bin"), "wb").write(qf.build_stub(ba_pa, entry_pa))

    mem_size = struct.unpack_from("<Q", payload, 0x40)[0]
    needed = phys_base + mem_size - 0x40000000
    ram_gib = max(4, -(-needed // (1 << 30)))

    cmd = [
        qf.QEMU, "-M", "virt,gic-version=3", "-cpu", "cortex-a76", "-smp", "1",
        "-m", f"{ram_gib}G", "-nographic", "-no-reboot",
        "-serial", f"file:{OUT}/serial.txt",
        "-qmp", "tcp:127.0.0.1:4455,server,nowait",
        "-d", "int", "-D", f"{OUT}/qemu.log",
        "-device", f"loader,file={OUT}/ram.bin,addr={phys_base:#x},force-raw=on",
        "-device", f"loader,file={OUT}/stub.bin,addr={qf.STUB_PA:#x},force-raw=on",
        "-device", f"loader,addr={qf.STUB_PA:#x},cpu-num=0",
    ]
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.PIPE)
    time.sleep(2)
    q = Qmp(4455)
    time.sleep(8)

    q.cmd("stop")

    def rdq(va):
        f = os.path.join(OUT, "tmp8.bin")
        q.cmd("pmemsave", val=phys_base + (va - virt_base), size=8, filename=f)
        return struct.unpack("<Q", open(f, "rb").read())[0]

    buf_base = rdq(0xFFFFFE0007AEF508)
    buf_ptr = rdq(0xFFFFFE0007AEF510)
    buf_size = rdq(0xFFFFFE0007AEF518)
    print(f"  debug_buf: base=0x{buf_base:x} ptr=0x{buf_ptr:x} size=0x{buf_size:x}")
    if buf_base and buf_size and buf_size < 0x100000:
        q.cmd("pmemsave", val=phys_base + (buf_base - virt_base), size=min(buf_size, 0x20000),
              filename=os.path.join(OUT, "debugbuf.bin"))
    for name, va in (("panicstr", PANIC_STR_VA), ("panicdata", PANIC_DATA_VA)):
        addr = phys_base + (va - virt_base)
        q.cmd("pmemsave", val=addr, size=0x400, filename=os.path.join(OUT, name + ".bin"))
    # debug_buf：panic 文本可能在这里
    for sym_va, tag in ((0xFFFFFE0007AEF508, "debu_buf_base"),):
        pass
    q.cmd("cont")
    p.kill()

    for name in ("panicstr", "panicdata"):
        path = os.path.join(OUT, name + ".bin")
        if not os.path.exists(path):
            print(f"  {name}: 没生成")
            continue
        d = open(path, "rb").read()
        txt = d.split(b"\0")[0]
        print(f"  {name}: len={len(d)}")
        if txt:
            print("    " + txt[:300].decode("latin1", "replace"))
        else:
            print("    (空)")
            # 当作指针再读一次
            ptr, = struct.unpack_from("<Q", d, 0)
            print(f"    第一个 qword = 0x{ptr:x}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
