#!/usr/bin/env python3
"""验证断点机制：在一个已知会被执行到的地址上下断点。"""

import os
import struct
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qemu_fuxi as qf
from gdbstub import Gdb

TARGET = 0xFFFFFE0007471020   # QEMU 里空闲循环反复执行的位置

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
    "-gdb", "tcp:127.0.0.1:1238", "-S",
    "-device", f"loader,file={out}/ram.bin,addr={phys_base:#x},force-raw=on",
    "-device", f"loader,file={out}/stub.bin,addr={qf.STUB_PA:#x},force-raw=on",
]
p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.PIPE)
time.sleep(2)

try:
    g = Gdb(1238, timeout=10)
    print("状态:", g.cmd("?"))
    print("在 0x%x 下断点:" % TARGET, g.set_bp(TARGET))
    g.cont()

    # 先跑 10 秒让内核启动，再中断看 PC
    time.sleep(10)
    g.interrupt()
    try:
        pkt = g._recv_packet()
        print("interrupt 后:", pkt)
    except Exception as e:
        print("interrupt 无响应:", e)
    r = g.regs()
    print("  pc=0x%x" % r["pc"])

    # 再继续，看断点是否触发
    print("继续 5 秒等断点 ...")
    g.cont()
    try:
        pkt, regs = g.wait_stop(timeout=5)
        print("  停止:", pkt, "pc=0x%x" % (regs["pc"] if regs else 0))
    except Exception as e:
        print("  断点未触发:", e)
finally:
    try:
        p.kill()
    except Exception:
        pass
