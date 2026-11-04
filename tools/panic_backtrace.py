#!/usr/bin/env python3
"""panic 之后走帧指针链，还原调用栈（QEMU + QMP）。"""

import os
import re
import struct
import subprocess
import sys
import time

sys.path.insert(0, r"E:\ios-on-fuxi\tools")
import qemu_fuxi as qf
from qemu_shim import Qmp
from dump_panic2 import load_syms

PAYLOAD = sys.argv[1] if len(sys.argv) > 1 else r"E:\download\payload-v7.bin"
KERNEL = sys.argv[2] if len(sys.argv) > 2 else r"E:\download\xnu-kernel-25\out\kernel.development.fuxi"
OUT = r"E:\qemurun"


def main() -> int:
    payload = open(PAYLOAD, "rb").read()
    syms = load_syms(KERNEL)
    items = sorted(syms.items(), key=lambda kv: kv[1])

    def sym(a):
        best = None
        for n, v in items:
            if v <= a:
                best = (v, n)
            else:
                break
        return "%s+0x%x" % (best[1], a - best[0]) if best else "?"

    virt_base, = struct.unpack_from("<Q", payload, 0x10)
    phys, img, ba, ep = qf.build_image(payload)
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "ram.bin"), "wb").write(img)
    open(os.path.join(OUT, "stub.bin"), "wb").write(qf.build_stub(ba, ep))
    ms = struct.unpack_from("<Q", payload, 0x40)[0]
    gib = max(4, -(-(phys + ms - 0x40000000) // (1 << 30)))

    cmd = [qf.QEMU, "-M", "virt,gic-version=3", "-cpu", "cortex-a76", "-smp", "1",
           "-m", f"{gib}G", "-nographic", "-no-reboot",
           "-qmp", "tcp:127.0.0.1:4465,server,nowait",
           "-device", f"loader,file={OUT}/ram.bin,addr={phys:#x},force-raw=on",
           "-device", f"loader,file={OUT}/stub.bin,addr={qf.STUB_PA:#x},force-raw=on",
           "-device", f"loader,addr={qf.STUB_PA:#x},cpu-num=0"]
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.PIPE)
    time.sleep(2)
    q = Qmp(4465)
    time.sleep(10)
    q.cmd("stop")

    r = q.cmd("human-monitor-command", **{"command-line": "info registers"})
    txt = r.get("return", "")
    regs = {}
    for m in re.finditer(r"\b(X\d\d|PC|SP|FP|LR|X29|X30)\s*=\s*([0-9a-fA-F]{8,16})", txt):
        regs[m.group(1)] = int(m.group(2), 16)
    pc = regs.get("PC", 0)
    sp = regs.get("SP", 0)
    fp = regs.get("X29", regs.get("FP", 0))
    print(f"  PC=0x{pc:x} -> {sym(pc)}")
    print(f"  SP=0x{sp:x}  FP=0x{fp:x}")
    print(f"  LR=0x{regs.get('X30', regs.get('LR', 0)):x} -> {sym(regs.get('X30', regs.get('LR', 0)))}")
    print()
    print("  帧指针链:")

    def rd(va, n):
        f = os.path.join(OUT, "t.bin")
        q.cmd("pmemsave", val=phys + (va - virt_base), size=n, filename=f)
        return open(f, "rb").read()

    cur = fp
    seen = set()
    for depth in range(24):
        if cur == 0 or cur in seen or not (virt_base <= cur < virt_base + 0x20000000):
            break
        seen.add(cur)
        try:
            frame = rd(cur, 16)
        except Exception:
            break
        if len(frame) < 16:
            break
        next_fp, lr = struct.unpack("<QQ", frame)
        print(f"   #{depth:<2} fp=0x{cur:x} lr=0x{lr:x}  {sym(lr)}")
        if next_fp <= cur:
            break
        cur = next_fp

    p.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
