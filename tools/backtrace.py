#!/usr/bin/env python3
"""中断 QEMU 里的内核，沿帧指针链回溯调用栈并符号化。

不用断点（这套 QEMU 上不稳定），直接从 x29 链读出返回地址，再对照内核符号表。
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
from gdb_probe import load_symbols


def symbolize(syms_sorted, addr):
    best = None
    for v, n in syms_sorted:
        if v <= addr:
            best = (v, n)
        else:
            break
    return f"{best[1]}+0x{addr - best[0]:x}" if best else f"0x{addr:x}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("payload")
    ap.add_argument("kernel")
    ap.add_argument("--outdir", default=r"E:\qemugdb")
    ap.add_argument("--wait", type=float, default=12)
    ap.add_argument("--gdbport", type=int, default=1239)
    a = ap.parse_args()

    syms, _ = load_symbols(a.kernel)
    syms_sorted = sorted(syms.items(), key=lambda kv: kv[1])
    by_value = sorted(((v, n) for n, v in syms.items()), key=lambda t: t[0])

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
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.PIPE)
    time.sleep(2)
    if p.poll() is not None:
        print("QEMU 退出:", p.stderr.read().decode("utf-8", "replace")[-1000:])
        return 1

    try:
        g = Gdb(a.gdbport, timeout=10)
        g.cont()
        print(f"运行 {a.wait} 秒后中断 ...")
        time.sleep(a.wait)
        g.interrupt()
        try:
            pkt = g._recv_packet()
            print("  停止:", pkt)
        except Exception as e:
            print("  中断无响应:", e)

        r = g.regs()
        print("  pc=0x%x  lr=0x%x  sp=0x%x  fp=0x%x" % (r["pc"], r["lr"], r["sp"], r["fp"]))
        print("  pc ->", symbolize(by_value, r["pc"]))
        print("  lr ->", symbolize(by_value, r["lr"]))
        print()
        print("调用栈（帧指针链）:")

        fp = r["fp"]
        seen = set()
        for depth in range(20):
            if fp < 0xfffffe0000000000 or fp in seen:
                break
            seen.add(fp)
            try:
                frame = g.read_mem(fp, 16)
            except Exception:
                break
            if len(frame) < 16:
                break
            next_fp, ret = struct.unpack("<QQ", frame)
            print(f"  #{depth:<2} {symbolize(by_value, ret)}   (lr=0x{ret:x})")
            if next_fp <= fp:
                break
            fp = next_fp
    finally:
        try:
            p.kill()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
