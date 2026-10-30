#!/usr/bin/env python3
"""在 QEMU 里跑完整的 fuxi shim Image（含内嵌 payload）。

和 qemu_fuxi.py 的区别：那个只跑 payload（自己造 boot_args），
这个跑整个 shim，让 shim 自己解析 payload、建 boot_args、跳内核——
和真机上 ABL 的行为一致。
"""

import os
import struct
import subprocess
import sys
import time

sys.path.insert(0, r"E:\ios-on-fuxi\tools")
import qemu_fuxi as qf
from qemu_shim import Qmp

SHIM_LOAD = 0x48000000   # 避开 QEMU 默认的 dtb 区域（0x40000000 起 1MB）
DTB_PA = 0x40000000      # QEMU virt 默认把 dtb 放在这里，x0 传它（ABL 也是这样）
STUB_PA = 0x40200000   # 与 qemu_fuxi.py 一致，已验证可执行


def build_enter_stub(target, x0=0):
    """ldr x0, =x0 ; ldr x1, =target ; br x1 ; nop ; .quad x0 ; .quad target"""
    return struct.pack("<4I2Q", 0x58000060, 0x58000081, 0xD61F0020, 0xD503201F, x0, target)


def main() -> int:
    image_path = sys.argv[1] if len(sys.argv) > 1 else r"E:\download\shim-new-qemu.bin"
    out = sys.argv[2] if len(sys.argv) > 2 else r"E:\qemushim"
    secs = int(sys.argv[3]) if len(sys.argv) > 3 else 20

    img = open(image_path, "rb").read()
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, "shim.bin"), "wb").write(img)
    open(os.path.join(out, "stub.bin"), "wb").write(build_enter_stub(SHIM_LOAD + 0x800, DTB_PA))

    fb = qf.FB_BASE_DEFAULT
    cmd = [
        qf.QEMU, "-M", "virt,gic-version=3", "-cpu", "cortex-a76", "-smp", "1",
        "-m", "4G", "-nographic", "-no-reboot",
        "-serial", f"file:{out}/serial.txt",
        "-qmp", "tcp:127.0.0.1:4471,server,nowait",
        "-d", "int,guest_errors", "-D", f"{out}/qemu.log",
        "-kernel", f"{out}/shim.bin",
    ]
    print(f"  加载 shim 到 0x{SHIM_LOAD:x}（{len(img):,} 字节），入口 0x{SHIM_LOAD + 0x800:x}")
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.PIPE)
    time.sleep(1.5)
    q = Qmp(4471)

    def read_pc():
        r = q.cmd("human-monitor-command", **{"command-line": "info registers"})
        for line in r.get("return", "").split("\n"):
            if "PC=" in line:
                return line.split("PC=")[1].split()[0].strip().rstrip(",")
        return "?"

    # 尽早看一次
    q.cmd("stop")
    print("  早期 PC:", read_pc())
    q.cmd("cont")

    # 分段采样，找出第一次异常发生的大致时刻
    deadline = time.time() + secs
    samples = []
    while time.time() < deadline:
        q.cmd("stop")
        pc = read_pc()
        samples.append(pc)
        q.cmd("cont")
        time.sleep(0.4)
    print("  分段 PC:", samples[:12])

    time.sleep(0.2)

    # 采样 PC
    try:
        q.cmd("stop")
        seen = []
        for _ in range(3):
            r = q.cmd("human-monitor-command", **{"command-line": "info registers"})
            txt = r.get("return", "")
            for line in txt.split("\n"):
                if "PC=" in line:
                    pc = line.split("PC=")[1].split()[0].strip().rstrip(",")
                    seen.append(pc)
                    break
            q.cmd("cont")
            time.sleep(0.3)
        print("  PC 采样:", seen)
        # dump 寄存器
        r = q.cmd("human-monitor-command", **{"command-line": "info registers"})
        regs = {}
        for line in r.get("return","").split("\n"):
            import re
            for m in re.finditer(r'\b(X\d+|PC|SP|X30)\s*=\s*([0-9a-f]+)', line):
                regs[m.group(1)] = int(m.group(2), 16)
        for k in ("PC","X0","X1","X2","X3","X19","X20","X21","X22","X27","X30"):
            if k in regs:
                print("    %s = 0x%x" % (k, regs[k]))
        # 读 shim 里的 con_fb 变量（.data 段，物理地址直接读）
        try:
            f = os.path.join(out, "cfb.bin")
            # shim 加载在 0x40200000，con_fb 在 .data，先用 adrp 目标 0x40200000 附近
            for probe in (0x40206000, 0x40207000, 0x40208000, 0x40209000):
                q.cmd("pmemsave", val=probe, size=64, filename=f)
                raw = open(f,"rb").read()
                vals = [int.from_bytes(raw[i:i+8],"little") for i in range(0,64,8)]
                hits = [hex(v) for v in vals if v in (0xB8000000, 0xB0000000)]
                if hits:
                    print("    0x%x: %s" % (probe, vals[:8]))
        except Exception:
            pass
        q.cmd("stop")
        # 截屏
        fb_bytes = qf.FB_STRIDE * qf.FB_H
        q.cmd("pmemsave", val=fb, size=fb_bytes, filename=os.path.join(out, "fb.raw"))
        raw = open(os.path.join(out, "fb.raw"), "rb").read()
        qf.save_png(os.path.join(out, "fb.png"), raw, qf.FB_W, qf.FB_H)
        # 读 panic 相关的全局变量（phys 0x42000000，virt 0xfffffe0006000000）
        PHYS = 0x42000000
        VIRT = 0xfffffe0006000000
        def va2pa(va): return PHYS + (va - VIRT)
        for name, va in (("panicstr", 0xfffffe0007aef4d8),
                         ("panicbuf", 0xfffffe0007aef508)):
            try:
                fout = os.path.join(out, name + ".bin")
                q.cmd("pmemsave", val=va2pa(va), size=512, filename=fout)
                d = open(fout, "rb").read()
                txt = d.split(b"\x00")[0]
                if txt and all(32 <= c < 127 or c in (9,10,13) for c in txt):
                    print("  %s: %s" % (name, txt.decode("latin1")[:200]))
                else:
                    import struct as _s
                    ptr, = _s.unpack_from("<Q", d, 0)
                    print("  %s: ptr=0x%x" % (name, ptr))
                    if VIRT <= ptr < VIRT + 0x10000000:
                        q.cmd("pmemsave", val=va2pa(ptr), size=256, filename=fout)
                        d2 = open(fout, "rb").read()
                        t2 = d2.split(b"\x00")[0]
                        if t2: print("      -> %s" % t2.decode("latin1")[:200])
            except Exception as e:
                print("  %s: %s" % (name, e))
        print(f"  截屏: {out}\\fb.png")
    except Exception as e:
        print("  采样失败:", e)

    p.kill()
    # 打印 shim 自己画到帧缓冲上的最后几行
    serial = os.path.join(out, "serial.txt")
    if os.path.exists(serial) and os.path.getsize(serial) > 0:
        txt = open(serial, "rb").read().decode("utf-8", "replace")
        print("  串口:", txt[-400:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
