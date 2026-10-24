#!/usr/bin/env python3
"""测试 qemu gdbstub 通信是否正常。"""

import os
import struct
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qemu_fuxi as qf
from gdbstub import Gdb

payload = open(r"E:\ios-on-fuxi\rom\xnu\qemu-payload.bin", "rb").read()
out = r"E:\qemugdb"
os.makedirs(out, exist_ok=True)

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
    "-gdb", "tcp:127.0.0.1:1236", "-S",
    "-device", f"loader,file={out}/ram.bin,addr={phys_base:#x},force-raw=on",
    "-device", f"loader,file={out}/stub.bin,addr={qf.STUB_PA:#x},force-raw=on",
    "-device", f"loader,addr={qf.STUB_PA:#x},cpu-num=0",
]
p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.PIPE)
time.sleep(2)

try:
    g = Gdb(1236, timeout=5)
    print("连上了")

    print("问状态 ...")
    pkt = g.cmd("?")
    print("  状态:", pkt)
    r = g.regs()
    print("  pc=0x%x sp=0x%x" % (r["pc"], r["sp"]))

    print("设置断点（当前 PC）...")
    resp = g.set_bp(r["pc"])
    print("  Z0 回复:", resp)
    resp = g.clear_bp(r["pc"])
    print("  z0 回复:", resp)

    print("继续 2 秒后再次 interrupt ...")
    g.cont()
    time.sleep(2)
    g.interrupt()
    time.sleep(0.3)
    try:
        pkt = g._recv_packet()
        print("  回复:", pkt)
    except Exception as e:
        print("  没收到停止包:", e)
    r2 = g.regs()
    print("  pc=0x%x" % r2["pc"])
finally:
    try:
        p.kill()
    except Exception:
        pass
