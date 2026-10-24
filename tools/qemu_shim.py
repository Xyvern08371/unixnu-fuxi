#!/usr/bin/env python3
"""在 QEMU 里单独跑 shim（模拟 ABL 交接状态：EL1、MMU 关、x0=DTB）。

用途：把「ABL 拒绝 boot.img」和「shim 代码本身有问题」分开。
shim 的控制台写 0xB8000000（fuxi 的 splash 区），QEMU 里那是普通 RAM，
所以能像以前一样把它 dump 出来看文字。

用法: qemu_shim.py <Image> [--outdir DIR] [--secs 10]
"""

import argparse
import os
import socket
import struct
import subprocess
import sys
import time
import zlib

QEMU = r"C:\Program Files\qemu\qemu-system-aarch64.exe"
STUB_PA = 0x40200000
SHIM_PA = 0x48000000          # shim 加载地址
LOAD_PA = 0x41000000          # 避开 QEMU 自己放在 RAM 基址的 DTB
FB_BASE = 0xB8000000          # fuxi splash 区（shim 控制台）
FB_W, FB_H = 1080, 2400


def stub(entry_pa, dtb_pa):
    # ldr x0, =dtb ; ldr x1, =entry ; br x1 ; nop ; .quad dtb ; .quad entry
    return struct.pack("<4I2Q", 0x58000080, 0x580000A1, 0xD61F0020, 0xD503201F,
                       dtb_pa, entry_pa)


class Qmp:
    def __init__(self, port, timeout=10):
        self.s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        self.f = self.s.makefile("rwb", buffering=0)
        self._read()
        self.cmd("qmp_capabilities")

    def _read(self):
        while True:
            line = self.f.readline()
            if not line:
                raise EOFError
            import json
            msg = json.loads(line)
            if "event" in msg:
                continue
            return msg

    def cmd(self, name, **args):
        import json
        req = {"execute": name}
        if args:
            req["arguments"] = args
        self.f.write((json.dumps(req) + "\n").encode())
        return self._read()


def save_png(path, raw, w, h):
    stride = w * 4
    rows = []
    for y in range(h):
        line = raw[y * stride:(y + 1) * stride]
        rgb = bytearray(w * 3)
        rgb[0::3] = line[2::4]
        rgb[1::3] = line[1::4]
        rgb[2::3] = line[0::4]
        rows.append(b"\0" + bytes(rgb))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(b"".join(rows), 6)) + chunk(b"IEND", b"")
    open(path, "wb").write(png)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--outdir", default=r"E:\qemushim")
    ap.add_argument("--secs", type=float, default=10)
    ap.add_argument("--port", type=int, default=4466)
    a = ap.parse_args()

    img = open(a.image, "rb").read()
    os.makedirs(a.outdir, exist_ok=True)
    out = os.path.abspath(a.outdir)
    print(f"shim Image: {len(img):,} 字节 -> 加载到 0x{SHIM_PA:x}")

    ram = bytearray(SHIM_PA - LOAD_PA + len(img) + 0x1000)
    ram[SHIM_PA - LOAD_PA:SHIM_PA - LOAD_PA + len(img)] = img
    open(os.path.join(out, "ram.bin"), "wb").write(bytes(ram))
    open(os.path.join(out, "stub.bin"), "wb").write(stub(SHIM_PA, 0))

    serial = os.path.join(out, "serial.txt")
    cmd = [
        QEMU, "-M", "virt,gic-version=3", "-cpu", "cortex-a76", "-smp", "1", "-m", "4G",
        "-nographic", "-serial", f"file:{serial}",
        "-qmp", f"tcp:127.0.0.1:{a.port},server,nowait",
        "-d", "int,guest_errors,unimp", "-D", os.path.join(out, "qemu.log"),
        "-no-reboot",
        "-device", f"loader,file={out}/ram.bin,addr=0x{LOAD_PA:x},force-raw=on",
        "-device", f"loader,file={out}/stub.bin,addr={STUB_PA:#x},force-raw=on",
        "-device", f"loader,addr={STUB_PA:#x},cpu-num=0",
    ]
    print("启动 QEMU ...")
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.PIPE)
    time.sleep(2)
    if p.poll() is not None:
        print("QEMU 退出:", p.stderr.read().decode("utf-8", "replace")[-1500:])
        return 1

    q = Qmp(a.port)
    t0 = time.time()
    while p.poll() is None and time.time() - t0 < a.secs:
        time.sleep(0.2)

    pcs = []
    for _ in range(3):
        q.cmd("stop")
        r = q.cmd("human-monitor-command", **{"command-line": "info registers"})
        for line in r.get("return", "").split("\n"):
            if line.strip().startswith("PC="):
                pcs.append(line.split()[0])
                break
        q.cmd("cont")
        time.sleep(0.3)

    q.cmd("stop")
    q.cmd("pmemsave", val=FB_BASE, size=FB_W * 4 * FB_H,
          filename=os.path.join(out, "fb.raw"))
    raw = open(os.path.join(out, "fb.raw"), "rb").read()
    save_png(os.path.join(out, "fb.png"), raw, FB_W, FB_H)

    try:
        p.kill()
    except Exception:
        pass

    print("PC 采样:", pcs)
    print("屏幕: ", os.path.join(out, "fb.png"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
