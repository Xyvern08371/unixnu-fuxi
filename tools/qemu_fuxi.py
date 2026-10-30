#!/usr/bin/env python3
"""在 PC 上用 QEMU 跑我们的 XNU 内核（不需要真机、不需要刷机）。

改造自 ios-sweet 的 tools/qemu-sweet.py：
  · payload 魔数改成 FUXIXNU
  · QMP 走 TCP（Windows 没有 unix socket）
  · 不做字形识别，改成：抓串口 + 抓寄存器 + 检查帧缓冲区域的标记颜色

用法:
  qemu_fuxi.py <payload> <输出目录> [--secs 15] [--fb 0xB0000000]
"""

import argparse
import json
import os
import socket
import struct
import subprocess
import sys
import time
import zlib

QEMU = r"C:\Program Files\qemu\qemu-system-aarch64.exe"
PAGE = 0x4000
STUB_PA = 0x40200000
BOOT_LINE_LENGTH = 608
MAGIC = b"FUXIXNU"   # payload 里是 8 字节，末尾有 NUL


def build_image(payload):
    """把 payload 铺成一个从 phys_base 开始的 RAM 镜像。返回 (phys_base, img, ba_pa, entry_pa)。"""
    magic, ver, nsegs = struct.unpack_from("<8sII", payload, 0)
    assert magic[:7] == MAGIC and ver == 1, "不是 FUXIXNU v1 payload"
    virt_base, entry_va, adt_off, adt_size, kernel_end, phys_base, mem_size = \
        struct.unpack_from("<7Q", payload, 0x10)
    cmdline = payload[0x48:0x48 + BOOT_LINE_LENGTH]
    delta = phys_base - virt_base
    adt_pa = kernel_end + delta
    ba_pa = (adt_pa + adt_size + PAGE - 1) & ~(PAGE - 1)
    top = ba_pa + PAGE
    img = bytearray(top - phys_base)

    segs = []
    for i in range(nsegs):
        vmaddr, vmsize, foff, fsize = struct.unpack_from("<4Q", payload, 0x2A8 + 32 * i)
        o = vmaddr + delta - phys_base
        img[o:o + fsize] = payload[foff:foff + fsize]
        segs.append((vmaddr, vmsize))

    img[adt_pa - phys_base:adt_pa - phys_base + adt_size] = payload[adt_off:adt_off + adt_size]

    ba = struct.pack("<HH4x4Q6QI4xQI", 2, 2, virt_base, phys_base, mem_size, top,
                     FB_BASE_DEFAULT, 1, FB_STRIDE, FB_W, FB_H, 32, 0,
                     adt_pa - delta, adt_size)
    ba += cmdline + b"\0" * 4 + struct.pack("<QQ", 0, mem_size)
    assert len(ba) == 736, len(ba)
    img[ba_pa - phys_base:ba_pa - phys_base + len(ba)] = ba
    return phys_base, bytes(img), ba_pa, entry_va + delta


def build_stub(ba_pa, entry_pa):
    # ldr x0, =ba ; ldr x1, =entry ; br x1 ; nop ; .quad ba ; .quad entry
    return struct.pack("<4I2Q", 0x58000080, 0x580000A1, 0xD61F0020, 0xD503201F, ba_pa, entry_pa)


class Qmp:
    def __init__(self, port, timeout=10):
        self.s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        self.f = self.s.makefile("rwb", buffering=0)
        self._read()                      # greeting
        self.cmd("qmp_capabilities")

    def _read(self):
        while True:
            line = self.f.readline()
            if not line:
                raise EOFError
            msg = json.loads(line)
            if "event" in msg:
                continue
            return msg

    def cmd(self, name, **args):
        req = {"execute": name}
        if args:
            req["arguments"] = args
        self.f.write((json.dumps(req) + "\n").encode())
        return self._read()

    def close(self):
        try:
            self.f.close()
            self.s.close()
        except Exception:
            pass


FB_W, FB_H = 1080, 2400
FB_STRIDE = FB_W * 4
FB_BASE_DEFAULT = 0xB0000000


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


SMP = 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("payload")
    ap.add_argument("outdir")
    ap.add_argument("--secs", type=float, default=15)
    ap.add_argument("--port", type=int, default=4444)
    ap.add_argument("--cpu", default="cortex-a76")
    ap.add_argument("--fb", type=lambda s: int(s, 0), default=FB_BASE_DEFAULT)
    ap.add_argument("--hmp", action="append", default=[])
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--smp", type=int, default=1)
    a = ap.parse_args()

    global SMP
    SMP = a.smp
    payload = open(a.payload, "rb").read()
    os.makedirs(a.outdir, exist_ok=True)
    out = os.path.abspath(a.outdir)

    phys_base, img, ba_pa, entry_pa = build_image(payload)
    open(os.path.join(out, "ram.bin"), "wb").write(img)
    open(os.path.join(out, "stub.bin"), "wb").write(build_stub(ba_pa, entry_pa))
    print(f"phys_base={phys_base:#x} boot_args={ba_pa:#x} entry={entry_pa:#x} img={len(img):,}")

    mem_size = struct.unpack_from("<Q", payload, 0x40)[0]
    needed = phys_base + mem_size - 0x40000000
    ram_gib = max(4, -(-needed // (1 << 30)))
    print(f"QEMU RAM: {ram_gib}G（需要覆盖 {phys_base + mem_size:#x}）")

    serial = os.path.join(out, "serial.txt")
    cmd = [
        QEMU, "-M", "virt,gic-version=3", "-cpu", a.cpu, "-smp", str(SMP), "-m", f"{ram_gib}G",
        "-nographic", "-serial", f"file:{serial}",
        "-qmp", f"tcp:127.0.0.1:{a.port},server,nowait",
        "-d", "int,guest_errors,unimp", "-D", os.path.join(out, "qemu.log"),
        "-no-reboot",
        "-device", f"loader,file={out}/ram.bin,addr={phys_base:#x},force-raw=on",
        "-device", f"loader,file={out}/stub.bin,addr={STUB_PA:#x},force-raw=on",
        "-device", f"loader,addr={STUB_PA:#x},cpu-num=0",
    ]
    print("启动 QEMU ...")
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.PIPE)
    time.sleep(2.0)
    if p.poll() is not None:
        err = p.stderr.read().decode("utf-8", "replace")
        print("QEMU 启动即退出：\n" + err[-2000:])
        return 1

    try:
        q = Qmp(a.port)
    except Exception as exc:
        print("QMP 连接失败:", exc)
        p.kill()
        return 1

    t0 = time.time()
    while p.poll() is None and time.time() - t0 < a.secs:
        time.sleep(0.2)

    result = {"status": "qemu_exited", "rc": p.returncode}
    if p.poll() is None:
        try:
            # 多次采样 PC，判断内核是死循环还是活着
            pcs = []
            for k in range(4):
                q.cmd("stop")
                r = q.cmd("human-monitor-command", **{"command-line": "info registers"})
                txt = r.get("return", "")
                for line in txt.split(chr(10)):
                    if line.strip().startswith("PC="):
                        pcs.append(line.split()[0])
                        break
                q.cmd("cont")
                time.sleep(0.5)
            print("PC 采样:", pcs)
            q.cmd("stop")
            regs = q.cmd("human-monitor-command", **{"command-line": "info registers"})
            open(os.path.join(out, "regs.txt"), "w", encoding="utf-8").write(
                regs.get("return", json.dumps(regs, ensure_ascii=False)))
            # 抓帧缓冲区域（我们的标记就画在这里）
            fb_bytes = FB_STRIDE * FB_H
            q.cmd("pmemsave", val=a.fb, size=fb_bytes, filename=os.path.join(out, "fb.raw"))
            raw = open(os.path.join(out, "fb.raw"), "rb").read()
            save_png(os.path.join(out, "fb.png"), raw, FB_W, FB_H)
            result = {"status": "captured", "fb_png": os.path.join(out, "fb.png")}
        except Exception as exc:
            result = {"status": "qmp_error", "error": str(exc)}
        finally:
            try:
                p.kill()
            except Exception:
                pass
            q.close()

    open(os.path.join(out, "result.json"), "w").write(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    if os.path.exists(serial):
        txt = open(serial, "rb").read().decode("utf-8", "replace")
        print("\n=== 串口输出（前 3000 字符）===")
        print(txt[:3000] if txt.strip() else "(空)")
    print(f"\n产物目录: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
