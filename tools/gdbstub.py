#!/usr/bin/env python3
"""最小 GDB Remote Serial Protocol 客户端 —— 用于在 QEMU 里给 XNU 下断点、读内存。

不依赖 gdb，直接用 TCP 和 qemu 的 gdbstub 对话。

用法示例（在 python 里）：
    from gdbstub import Gdb
    g = Gdb(1235)
    g.regs()                       # 读所有寄存器
    g.set_bp(0xfffffe0007xxxxxx)   # 下断点
    g.cont()                       # 继续
    g.wait_stop(timeout=10)        # 等停下来，返回 {signal, pc}
"""

import socket
import struct
import time


class Gdb:
    def __init__(self, port=1235, host="127.0.0.1", timeout=5.0):
        self.s = socket.create_connection((host, port), timeout=timeout)
        self.s.settimeout(timeout)
        self.buf = b""

    # ---- 底层收发 ----
    def _recv_packet(self):
        while True:
            while not self.buf.startswith(b"$"):
                i = self.buf.find(b"$")
                if i < 0:
                    self.buf += self.s.recv(4096)
                    continue
                self.buf = self.buf[i:]
            # 找到 #xx
            j = self.buf.find(b"#")
            if j < 0:
                self.buf += self.s.recv(4096)
                continue
            body = self.buf[1:j]
            self.buf = self.buf[j + 3:]
            self.s.sendall(b"+")
            return body.decode("latin1")

    def _send(self, payload):
        data = payload.encode("latin1")
        csum = sum(data) & 0xFF
        self.s.sendall(b"$" + data + b"#" + ("%02x" % csum).encode())

    def cmd(self, payload, timeout=5.0):
        self.s.settimeout(timeout)
        self._send(payload)
        return self._recv_packet()

    # ---- 常用操作 ----
    def stop_reason(self):
        r = self.cmd("?")
        return r

    def regs(self):
        r = self.cmd("g")
        out = {}
        names = ["x0", "x1", "x2", "x3", "x4", "x5", "x6", "x7", "x8", "x9",
                 "x10", "x11", "x12", "x13", "x14", "x15", "x16", "x17", "x18",
                 "x19", "x20", "x21", "x22", "x23", "x24", "x25", "x26", "x27",
                 "x28", "fp", "lr", "sp", "pc"]
        for i, n in enumerate(names):
            if (i + 1) * 16 > len(r):
                break
            raw = r[i * 16:(i + 1) * 16]
            val = int.from_bytes(bytes.fromhex(raw), "little")
            out[n] = val
        return out

    def read_mem(self, addr, length):
        data = b""
        off = 0
        while off < length:
            chunk = min(0x1000, length - off)
            r = self.cmd("m%x,%x" % (addr + off, chunk))
            if r.startswith("E"):
                break
            data += bytes.fromhex(r)
            off += chunk
        return data

    def read_u64(self, addr):
        d = self.read_mem(addr, 8)
        return struct.unpack("<Q", d)[0] if len(d) == 8 else None

    def read_cstr(self, addr, maxlen=256):
        d = self.read_mem(addr, maxlen)
        z = d.find(b"\0")
        if z >= 0:
            d = d[:z]
        return d.decode("latin1", "replace")

    def set_bp(self, addr):
        return self.cmd("Z0,%x,4" % addr)

    def clear_bp(self, addr):
        return self.cmd("z0,%x,4" % addr)

    def cont(self):
        # 继续执行，不等待回复（回复会在停止时到来）
        self._send("c")

    def step(self):
        self._send("s")

    def wait_stop(self, timeout=10.0):
        """等目标停下，返回 (signal_text, regs)"""
        self.s.settimeout(timeout)
        pkt = self._recv_packet()
        regs = None
        try:
            regs = self.regs()
        except Exception:
            pass
        return pkt, regs

    def interrupt(self):
        self.s.sendall(b"\x03")

    def close(self):
        try:
            self.s.close()
        except Exception:
            pass
