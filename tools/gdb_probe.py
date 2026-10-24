#!/usr/bin/env python3
"""在 QEMU 里给 XNU 下断点，追踪它经过哪些关键函数。

用 -S 冻结启动，先下好断点再继续，避免"目标在跑时下断点无效"的问题。

用法:
  gdb_probe.py <payload> <kernel> [--secs 60] [--symbols a,b,c]
"""

import argparse
import os
import struct
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qemu_fuxi as qf
from gdbstub import Gdb


def load_symbols(kernel_path):
    buf = open(kernel_path, "rb").read()
    magic, cpu, sub, ftype, ncmds, sizeofcmds, flags, _ = struct.unpack_from("<8I", buf, 0)
    off = 32
    symtab = None
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", buf, off)
        if cmd == 0x2:
            symtab = struct.unpack_from("<4I", buf, off + 8)
        off += size
    symoff, nsyms, stroff, strsize = symtab
    syms = {}
    for i in range(nsyms):
        o = symoff + i * 16
        strx, ntype, sect, desc, value = struct.unpack_from("<IBBHQ", buf, o)
        if value == 0:
            continue
        end = buf.index(b"\0", stroff + strx)
        syms[buf[stroff + strx:end].decode("latin1")] = value
    return syms, buf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("payload")
    ap.add_argument("kernel")
    ap.add_argument("--outdir", default=r"E:\qemugdb")
    ap.add_argument("--secs", type=float, default=60)
    ap.add_argument("--gdbport", type=int, default=1237)
    ap.add_argument("--symbols", default="")
    a = ap.parse_args()

    syms, _ = load_symbols(a.kernel)

    default = ["_machine_startup", "_kernel_bootstrap", "_bsd_init", "_vfs_mountroot"]
    names = [s.strip() for s in a.symbols.split(",") if s.strip()] or default

    bps = {}
    for n in names:
        if n in syms:
            bps[n] = syms[n]
    print("断点:")
    for n, addr in sorted(bps.items(), key=lambda kv: kv[1]):
        print(f"  {n} = 0x{addr:x}")

    payload = open(a.payload, "rb").read()
    os.makedirs(a.outdir, exist_ok=True)
    out = os.path.abspath(a.outdir)
    phys_base, img, ba_pa, entry_pa = qf.build_image(payload)
    open(os.path.join(out, "ram.bin"), "wb").write(img)
    open(os.path.join(out, "stub.bin"), "wb").write(qf.build_stub(ba_pa, entry_pa))
    mem_size = struct.unpack_from("<Q", payload, 0x40)[0]
    needed = phys_base + mem_size - 0x40000000
    ram_gib = max(4, -(-needed // (1 << 30)))

    cmd = [
        qf.QEMU, "-M", "virt,gic-version=3", "-cpu", "cortex-a76", "-smp", "1",
        "-m", f"{ram_gib}G", "-nographic", "-no-reboot",
        "-serial", f"file:{os.path.join(out, 'serial.txt')}",
        "-gdb", f"tcp:127.0.0.1:{a.gdbport}", "-S",
        "-device", f"loader,file={out}/ram.bin,addr={phys_base:#x},force-raw=on",
        "-device", f"loader,file={out}/stub.bin,addr={qf.STUB_PA:#x},force-raw=on",
    ]
    print("启动 QEMU（冻结）...")
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.PIPE)
    time.sleep(2)
    if p.poll() is not None:
        print("QEMU 退出:", p.stderr.read().decode("utf-8", "replace")[-1200:])
        return 1

    hits = []
    try:
        g = Gdb(a.gdbport, timeout=10)
        print("gdbstub 已连接，状态:", g.cmd("?"))

        for n, addr in bps.items():
            r = g.set_bp(addr)
            if r != "OK":
                print(f"  ⚠ 断点 {n} 失败: {r}")

        print("继续执行 ...")
        g.cont()

        deadline = time.time() + a.secs
        while time.time() < deadline:
            try:
                pkt, regs = g.wait_stop(timeout=max(0.5, deadline - time.time()))
            except Exception:
                break
            if not regs:
                break
            pc = regs["pc"]
            name = next((n for n, ad in bps.items() if ad == pc), None)
            if name:
                hits.append(name)
                print(f"  ✅ 命中 {name}  (x0=0x{regs['x0']:x} x1=0x{regs['x1']:x})")
            else:
                print(f"  · 停在 0x{pc:x}（非断点，继续）")
            g.cont()
    finally:
        try:
            p.kill()
        except Exception:
            pass

    print()
    print("命中顺序:", " -> ".join(hits) if hits else "（没有任何断点命中）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
