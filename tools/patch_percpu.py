#!/usr/bin/env python3
"""在 payload 里修补内核：把 current_percpu_base() 变成不依赖 current_thread()。

原实现：
    current_percpu_base() { return current_thread()->machine.pcpu_data_base; }
真机冷启动时 current_thread() 返回 NULL（TPIDR_EL1 = 0），于是访问 0x220 崩溃。

改法：把 `bl _current_thread` + `ldr x0,[x0,#0x220]` 这两条（8 字节）
替换成从全局变量 `_percpu_base.start` 直接加载：
    adrp x0, _percpu_base + 0x???  ... 需要 2 条 + ldr = 12 字节，放不下。

所以改为：把整个函数前 12 字节换成
    mov  x0, #<percpu_base 地址低 16 位>
    movk x0, #<...>, lsl #16
    ret
然后让调用者读到的是 percpu_base 结构体的地址，而不是它的 start 字段。
这在数学上不等价，但用于早期启动足够：内核随后会自己把 current_thread 设好，
之后就不再走这条被改坏的路径。

更安全的做法：只把 `ldr x0, [x0, #0x220]` 换成 `mov x0, #0`（不改变控制流）。
这样 current_percpu_base() 返回 0，而调用方 vm_page_grab 只是把返回值当 key 用，
真正解引用它的地方（PERCPU_GET_WITH_BASE）会因为 address 为 0 而 panic——
所以还是不行。

最终选择：把函数体整体替换成
    movz x0, #<addr & 0xffff>
    movk x0, #<addr >> 16>, lsl #16
    movk x0, #<addr >> 32>, lsl #32
    movk x0, #<addr >> 48>, lsl #48
    ret
    4 条 mov + 1 条 ret = 20 字节 > 24 字节函数体，放得下！
（函数总长 0x18 = 24 字节）
"""

import struct
import sys

KERNEL = r"E:\ios-on-fuxi\rom\xnu\kernel.development.fuxi"
sys.path.insert(0, r"E:\ios-on-fuxi\tools")
from dump_panic2 import load_syms  # noqa: E402

NOP = 0xD503201F
RET = 0xD65F03C0


def movz(rd, imm16, shift=0):
    return 0xD2800000 | (imm16 << 5) | (rd) | ((shift // 16) << 21)


def movk(rd, imm16, shift=0):
    return 0xF2800000 | (imm16 << 5) | (rd) | ((shift // 16) << 21)


def patch(kernel_path, out_path):
    d = bytearray(open(kernel_path, "rb").read())
    syms = load_syms(kernel_path)

    ncmds, = struct.unpack_from("<I", d, 16)
    p, segs = 32, []
    for _ in range(ncmds):
        cmd, ln = struct.unpack_from("<II", d, p)
        if cmd == 0x19 and ln >= 72:
            nm = d[p + 8:p + 24].split(b"\0")[0].decode()
            va, vs, fo, fs = struct.unpack_from("<4Q", d, p + 24)
            segs.append((nm, va, fs, fo))
        p += ln

    def fileoff(va):
        for nm, sva, fs, fo in segs:
            if sva <= va < sva + fs:
                return fo + (va - sva), nm
        return None, None

    fn = syms["_current_percpu_base"]
    # percpu_base 结构体：start 在偏移 0（struct percpu_base { start, size, end }）
    target = syms["_percpu_base"]
    off, seg = fileoff(fn)
    if off is None:
        raise SystemExit("找不到函数")

    words = [movz(0, target & 0xffff),
             movk(0, (target >> 16) & 0xffff, 16),
             movk(0, (target >> 32) & 0xffff, 32),
             movk(0, (target >> 48) & 0xffff, 48)]
    # 第 5 条：ldr x0, [x0]   —— percpu_base.start
    words.append(0xF9400000)
    words.append(RET)
    while len(words) < 6:
        words.append(NOP)

    print(f"  函数 0x{fn:x} ({seg}) 文件偏移 0x{off:x}")
    print(f"  percpu_base = 0x{target:x}")
    for k, w in enumerate(words):
        old, = struct.unpack_from("<I", d, off + 4 * k)
        print(f"    +{k*4:02x} 0x{old:08X} -> 0x{w:08X}")
        struct.pack_into("<I", d, off + 4 * k, w)

    open(out_path, "wb").write(bytes(d))
    print(f"  已写 {out_path}")


if __name__ == "__main__":
    patch(sys.argv[1] if len(sys.argv) > 1 else KERNEL,
          sys.argv[2] if len(sys.argv) > 2 else r"E:\download\kernel-patched.fuxi")
