#!/usr/bin/env python3
"""把 Apple kernelcache 里选定的组件（默认 APFS 及其依赖）预链接进我们的内核。

做法：
  1. 用 UniXNU 的 plan() 计算组件选择、段范围、指针绑定（容错解析）
  2. 选一个统一的 slide，让所有组件段落进内核为 kext 预留的 48MB 区间
     （该区间在 __PRELINK_TEXT 起始到内核 __TEXT 起始之间）
  3. 把组件段数据追加到文件末尾（不改动原有段的文件偏移，符号表仍然有效），
     并把 __PRELINK_TEXT / __PLK_* / __PRELINK_DATA / __PRELINK_INFO 段的大小和
     偏移改成真实值
  4. 按绑定表重写 12k+ 个指针
  5. 重写 __PRELINK_INFO 里的 plist（组件清单，加载地址用新 VA）
  6. 输出 kernel.macho
"""

import io
import struct
import sys
import zipfile

sys.path.insert(0, r"E:\download\UniXNU\kits\NativePrelink")
sys.path.insert(0, r"E:\ios-on-fuxi\tools")

from prelink_try2 import (load_kc, normalize_info, strip_ctf, tolerant_macho,
                          KC_KERNEL_OFF, IPSW, ENTRY)

OURS = r"E:\download\xnu-kernel-22\out\kernel.development.fuxi"
OUT = r"E:\download\kernel-prelinked.macho"
PAGE = 0x4000                 # 16K 页粒度（我们的内核）
COALESCED = {"__PRELINK_TEXT": "__TEXT", "__PLK_TEXT_EXEC": "__TEXT_EXEC",
             "__PRELINK_DATA": "__DATA", "__PLK_DATA_CONST": "__DATA_CONST"}
CONTAINERS = ["__PRELINK_TEXT", "__PLK_TEXT_EXEC", "__PLK_DATA_CONST",
              "__PRELINK_DATA", "__PRELINK_INFO"]


def align(x, a=PAGE):
    return (x + a - 1) & ~(a - 1)


def seg_by_name(m, name):
    for s in m["segments"]:
        if s["name"] == name:
            return s
    return None


def main() -> int:
    import native_prelink as np
    np.macho = tolerant_macho

    print("加载 Apple kernelcache ...")
    kc = load_kc()
    original = bytes(normalize_info(bytearray(kc[KC_KERNEL_OFF:])))

    print("加载我们的内核 ...")
    native = bytes(strip_ctf(bytearray(io.open(OURS, "rb").read())))
    nm = tolerant_macho(native)

    text = seg_by_name(nm, "__TEXT")
    pre = seg_by_name(nm, "__PRELINK_TEXT")
    print(f"  内核 __TEXT      @ 0x{text['va']:x}")
    print(f"  预留区 __PRELINK_TEXT @ 0x{pre['va']:x}")

    orig_kernel = tolerant_macho(original)
    apple_text = seg_by_name(orig_kernel, "__TEXT")
    apple_pre = seg_by_name(orig_kernel, "__PRELINK_TEXT")
    # 让 Apple 的 __PRELINK_TEXT 起点对齐到我们预留区的起点，
    # 这样所有组件段都落在 [预留区起点, 内核 __TEXT) 之内
    base_slide = pre["va"] - apple_pre["va"]
    print(f"  Apple __PRELINK_TEXT @ 0x{apple_pre['va']:x}")
    print(f"  初始 slide = {base_slide:+#x}（组件块对齐预留区起点）")

    # 第一次规划：只为拿到组件段范围（用一个占位绑定）
    def noop_binding(address, original_exports, native_by_name):
        return text["va"]

    real_ukb = np.unique_kernel_binding
    np.unique_kernel_binding = noop_binding
    probe = np.plan(native, original, ["com.apple.filesystems.apfs"], base_slide)

    starts = [e["va"] for e in probe["extents"]]
    ends = [e["va"] + e["size"] for e in probe["extents"]]
    lo, hi = min(starts), max(ends)
    print(f"  组件段范围（slide 后）: 0x{lo:x} .. 0x{hi:x}  共 {(hi - lo) / 1048576:.1f} MB")

    # 预留区：[pre.va, text.va)
    room_lo, room_hi = pre["va"], text["va"]
    need = hi - lo
    if need > room_hi - room_lo:
        print("  ✗ 组件比预留区还大，需要换策略")
        return 1
    # 让组件块从预留区起点开始，尽量紧凑
    shift = room_lo - lo
    slide = base_slide + shift
    # slide 必须 16K 对齐：向上取整，move 后仍在预留区内
    slide = (slide + PAGE - 1) & ~(PAGE - 1)
    print(f"  最终 slide = {slide:+#x}（组件块 0x{lo + (slide - base_slide):x} .. 0x{hi + (slide - base_slide):x}）")

    if slide % PAGE:
        print("  ✗ slide 不是 16K 对齐")
        return 1

    # 正式规划：用真实的内核符号解析
    np.unique_kernel_binding = real_ukb
    r = np.plan(native, original, ["com.apple.filesystems.apfs"], slide)
    print(f"  组件 {len(r['components'])}，绑定 {r['pointer_counts']}")

    # ---- 准备输出 ----
    img = bytearray(native)
    new_file_end = len(img)
    seg_updates = {}      # name -> (va, vsize, fileoff, filesize)

    by_container = {c: [] for c in CONTAINERS}
    for e in r["extents"]:
        for container, src in COALESCED.items():
            pass
        # 段名到容器段的映射：extents 里带 segment 名
        src = e["segment"]
        container = next((c for c, s in COALESCED.items() if s == src), None)
        if container is None:
            # __LINKEDIT 等跳过
            continue
        by_container[container].append(e)

    print("\n  各容器段将装入：")
    for c in CONTAINERS:
        items = by_container[c]
        if items:
            lo2 = min(i["va"] for i in items)
            hi2 = max(i["va"] + i["size"] for i in items)
            print(f"    {c:<18} {len(items):>2} 段  0x{lo2:x} .. 0x{hi2:x}  ({(hi2-lo2)/1024:.0f} KB)")

    # 组件数据从原 kernelcache 里取（extents 记录的是 origin Va；用 tolerant 解析原始镜像定位）
    def data_for(container, items):
        if not items:
            return b"", None, None
        lo2 = min(i["va"] for i in items) & ~(PAGE - 1)   # 段起点按 16K 对齐
        hi2 = max(i["va"] + i["size"] for i in items)
        vsize = align(hi2 - lo2)
        buf = bytearray(vsize)
        for it in items:
            # 原始镜像里该段的文件数据
            oseg = None
            for s in orig_kernel["segments"]:
                base = s["va"]
                # 组件段的原始 VA = 新的 va - slide
                if base <= (it["va"] - slide) < base + s["size"]:
                    oseg = s
                    break
            if not oseg:
                continue
            off_in = oseg["fileoff"] + (it["va"] - slide) - oseg["va"]
            chunk = original[off_in:off_in + it["size"]]
            at = it["va"] - lo2
            buf[at:at + len(chunk)] = chunk
        return bytes(buf), lo2, vsize

    for c in CONTAINERS:
        if c == "__PRELINK_INFO":
            continue
        data, va, vsize = data_for(c, by_container[c])
        if not data:
            continue
        fileoff = align(new_file_end)
        img += b"\0" * (fileoff - len(img))
        img += data
        new_file_end = len(img)
        seg_updates[c] = (va, vsize, fileoff, len(data))
        print(f"  {c:<18} 写入 {len(data):>9,} 字节 @file 0x{fileoff:x}")

    # __PRELINK_INFO：重新生成 plist（只保留选中组件）
    print("\n  生成 __PRELINK_INFO ...")
    entries = r["components"]
    # 从原始 XML 里取出这些组件的条目（简单起见先放一个最小可用的 plist）
    xml = ('<?xml version="1.0" encoding="UTF-8"?><dict>'
           '<key>_PrelinkInfoDictionary</key><array>')
    for c in entries:
        xml += ('<dict><key>CFBundleIdentifier</key><string>%s</string>'
                '<key>OSBundleLibraries</key><dict/></dict>' % c)
    xml += "</array></dict>"
    info_bytes = xml.encode()
    fileoff = align(new_file_end)
    img += b"\0" * (fileoff - len(img))
    img += info_bytes
    new_file_end = len(img)
    # 放到整个组件块之后（16K 对齐），避免与 __PRELINK_TEXT 重叠
    block_end = max(v[0] + v[1] for v in seg_updates.values()) if seg_updates else pre["va"]
    info_va = align(block_end)
    if info_va + align(len(info_bytes)) > text["va"]:
        print("  ✗ __PRELINK_INFO 放不下（超出内核 __TEXT 起点）")
        return 1
    seg_updates["__PRELINK_INFO"] = (info_va, align(len(info_bytes)), fileoff, len(info_bytes))
    print(f"  __PRELINK_INFO     {len(info_bytes):,} 字节 @va 0x{info_va:x} @file 0x{fileoff:x}")

    # ---- 更新段头 ----
    print("\n  更新段头 ...")
    ncmds, = struct.unpack_from("<I", img, 16)
    p = 32
    for _ in range(ncmds):
        cmd, length = struct.unpack_from("<II", img, p)
        if cmd == 0x19 and length >= 72:
            name = bytes(img[p + 8:p + 24]).split(b"\0")[0].decode()
            if name in seg_updates:
                va, vsize, foff, fsize = seg_updates[name]
                struct.pack_into("<Q", img, p + 24, va)
                struct.pack_into("<Q", img, p + 32, vsize)
                struct.pack_into("<Q", img, p + 40, foff)
                struct.pack_into("<Q", img, p + 48, fsize)
                print(f"    {name:<18} va=0x{va:x} vsize=0x{vsize:x} file=0x{foff:x}/{fsize:,}")
        p += length

    # ---- 重绑指针 ----
    print("\n  重绑指针 ...")
    # 建立 旧VA -> 新VA 的映射（组件段）
    ranges = [(e["va"] - slide, e["va"], e["size"]) for e in r["extents"]]

    def remap(old_va):
        for o, n, size in ranges:
            if o <= old_va < o + size:
                return n + (old_va - o)
        return None

    # site 也要跟着搬：site 原 VA -> 新 VA
    applied = 0
    for b in r["bindings"]:
        new_site = remap(b["site"])
        if new_site is None:
            continue
        # site 落在组件数据缓冲里，需要换算成文件偏移
        # 找它属于哪个容器段
        foff = None
        for cname, items in by_container.items():
            if not items:
                continue
            lo2 = min(i["va"] for i in items)
            hi2 = max(i["va"] + i["size"] for i in items)
            if lo2 <= new_site < hi2:
                va, vsize, fo, fs = seg_updates[cname]
                foff = fo + (new_site - va)
                break
        if foff is None:
            continue
        target = b["new_target"]
        if b["kind"] == "component":
            remapped = remap(b["new_target"])
            if remapped is not None:
                target = remapped
        struct.pack_into("<Q", img, foff, target)
        applied += 1
    print(f"    已重绑 {applied} / {len(r['bindings'])} 处")

    io.open(OUT, "wb").write(bytes(img))
    print(f"\n✅ 输出 {OUT}（{len(img):,} 字节）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
