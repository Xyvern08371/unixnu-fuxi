#!/usr/bin/env python3
"""bootimg.py -- 安卓引导镜像解析器 (boot / vendor_boot / dtbo)

用途: 从刷机包里抽出 DTB、内核、ramdisk, 不需要手机、不需要 root、不需要 adb。

支持:
  * boot.img    header v3 / v4  (fuxi 这类 SM8550 设备用的就是 v4)
  * vendor_boot header v3 / v4  (DTB 在这里)
  * dtbo        设备树覆盖分区 (dt_table, 一份镜像里可能有多份 DTB)

不支持 v0-v2 的 boot(老设备用的, 结构不同), 遇到会明确报错而不是乱解。

用法:
  python bootimg.py info    boot.img
  python bootimg.py extract boot.img -o out/
"""
from __future__ import annotations

import argparse
import os
import struct
import sys

BOOT_MAGIC = b"ANDROID!"
VENDOR_MAGIC = b"VNDRBOOT"
DTBO_MAGIC = 0xD7B7AB1E
FDT_MAGIC = 0xD00DFEED

PAGE = 4096


class ImgError(ValueError):
    pass


def align(n: int, page: int = PAGE) -> int:
    return (n + page - 1) // page * page


def _cstr(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("utf-8", "replace")


def _fdt_summary(blob: bytes) -> str:
    """不依赖 apple_dt, 只读 FDT 头, 给出大小与版本。"""
    if len(blob) < 40 or struct.unpack(">I", blob[:4])[0] != FDT_MAGIC:
        return "不是 FDT"
    total, = struct.unpack(">I", blob[4:8])
    return "FDT v%d, %d 字节" % (struct.unpack(">I", blob[20:24])[0], total)


# ---------------------------------------------------------------- boot.img

def parse_boot(data: bytes) -> dict:
    if data[:8] != BOOT_MAGIC:
        raise ImgError("不是 boot.img (magic=%r)" % data[:8])
    if len(data) < 64:
        raise ImgError("文件太短: %d 字节" % len(data))

    # v0-v2 与 v3/v4 是两套完全不同的头部布局, 先判断是哪一套:
    #   v0-v2 在偏移 36 有 page_size(512~65536)
    #   v3/v4 的偏移 36 落在 reserved 区, 恒为 0
    cand_page, = struct.unpack("<I", data[36:40])
    if 512 <= cand_page <= 65536:
        return _parse_boot_legacy(data, cand_page)

    (kernel_size, ramdisk_size, os_version,
     header_size) = struct.unpack("<4I", data[8:24])
    header_version, = struct.unpack("<I", data[40:44])
    cmdline = _cstr(data[44:44 + 1536])

    out = {
        "kind": "boot",
        "header_version": header_version,
        "header_size": header_size,
        "kernel_size": kernel_size,
        "ramdisk_size": ramdisk_size,
        "os_version": "0x%08x" % os_version,
        "cmdline": cmdline,
    }

    if header_version in (3, 4):
        page = PAGE
        pos = align(header_size, page)
        out["kernel"] = data[pos:pos + kernel_size]
        out["kernel_gzip"] = out["kernel"][:2] == b"\x1f\x8b"
        pos = align(pos + kernel_size, page)
        out["ramdisk"] = data[pos:pos + ramdisk_size]
        pos = align(pos + ramdisk_size, page)
        if header_version == 4:
            sig_size, = struct.unpack("<I", data[1580:1584])
            out["signature_size"] = sig_size
            out["signature"] = data[pos:pos + sig_size]
        return out

    raise ImgError("未知 boot header 版本: %d" % header_version)


# ---------------------------------------------------------------- boot v0/v1/v2

def _parse_boot_legacy(data: bytes, page: int) -> dict:
    """boot header v0/v1/v2 —— Renegade 的 boot-<device>.img 用的就是 v1。

    头部 1632/1648/1660 字节, 按 page_size 对齐后依次是
    kernel / ramdisk / second / recovery_dtbo(v1+) / dtb(v2+)。
    """
    u32 = lambda off: struct.unpack("<I", data[off:off + 4])[0]

    kernel_size = u32(8)
    kernel_addr = u32(12)
    ramdisk_size = u32(16)
    ramdisk_addr = u32(20)
    second_size = u32(24)
    header_version = u32(40)
    if header_version > 2:
        raise ImgError("偏移 36 像 page_size 但 header_version=%d, 格式可疑" % header_version)

    out = {
        "kind": "boot",
        "header_version": header_version,
        "page_size": page,
        "kernel_size": kernel_size,
        "kernel_addr": "0x%x" % kernel_addr,
        "ramdisk_size": ramdisk_size,
        "ramdisk_addr": "0x%x" % ramdisk_addr,
        "second_size": second_size,
        "os_version": "0x%08x" % u32(44),
        "name": _cstr(data[48:64]),
        "cmdline": _cstr(data[64:576]),
    }

    pos = align(page, page)
    out["kernel"] = data[pos:pos + kernel_size]
    out["kernel_gzip"] = out["kernel"][:2] == b"\x1f\x8b"
    pos = align(pos + kernel_size, page)
    out["ramdisk"] = data[pos:pos + ramdisk_size]
    pos = align(pos + ramdisk_size, page)
    out["second"] = data[pos:pos + second_size]
    pos = align(pos + second_size, page)

    if header_version >= 1 and len(data) >= 1648:
        rec_size = u32(1632)
        out["recovery_dtbo_size"] = rec_size
        out["recovery_dtbo"] = data[pos:pos + rec_size]
        pos = align(pos + rec_size, page)

    if header_version >= 2 and len(data) >= 1660:
        dtb_size = u32(1648)
        out["dtb"] = data[pos:pos + dtb_size]

    return out


# ---------------------------------------------------------------- vendor_boot

def split_fdt(blob: bytes) -> list[bytes]:
    """vendor_boot 的 dtb 段里往往是多份 FDT 首尾相接(fuxi 有 5 份)。
    按头部 total 长度切开; 遇到对不齐的垃圾就跳过 4 字节继续找。"""
    out = []
    i = 0
    while i < len(blob) - 40:
        if blob[i:i + 4] == b"\xd0\x0d\xfe\xed":
            total, = struct.unpack(">I", blob[i + 4:i + 8])
            if 40 < total <= len(blob) - i:
                out.append(blob[i:i + total])
                i += (total + 3) // 4 * 4
                continue
        i += 4
    return out


def parse_vendor_boot(data: bytes) -> dict:
    if data[:8] != VENDOR_MAGIC:
        raise ImgError("不是 vendor_boot.img (magic=%r)" % data[:8])

    header_version, = struct.unpack("<I", data[8:12])
    page_size, = struct.unpack("<I", data[12:16])
    vendor_ramdisk_size, = struct.unpack("<I", data[24:28])
    cmdline = _cstr(data[28:28 + 2048])
    header_size, = struct.unpack("<I", data[2096:2100])
    dtb_size, = struct.unpack("<I", data[2100:2104])
    dtb_addr, = struct.unpack("<Q", data[2104:2112])

    out = {
        "kind": "vendor_boot",
        "header_version": header_version,
        "page_size": page_size,
        "header_size": header_size,
        "vendor_ramdisk_size": vendor_ramdisk_size,
        "dtb_size": dtb_size,
        "dtb_addr": "0x%x" % dtb_addr,
        "cmdline": cmdline,
    }

    page = page_size or PAGE
    pos = align(header_size, page)
    out["vendor_ramdisk"] = data[pos:pos + vendor_ramdisk_size]
    pos = align(pos + vendor_ramdisk_size, page)
    dtb_blob = data[pos:pos + dtb_size]
    out["dtb_blob"] = dtb_blob
    out["dtbs"] = split_fdt(dtb_blob)
    out["dtb"] = out["dtbs"][0] if out["dtbs"] else b""
    return out


# ---------------------------------------------------------------- dtbo

def parse_dtbo(data: bytes) -> dict:
    # 注意: dt_table 的头与条目都是【大端】(AOSP mkdtimg 用 cpu_to_fdt32),
    # 和 boot/vendor_boot 的小端正好相反。这个坑踩过。
    magic, total_size, header_size, entry_size, entry_count, \
        entries_offset, page_size, version = struct.unpack(">8I", data[:32])
    if magic != DTBO_MAGIC:
        raise ImgError("不是 dtbo.img (magic=0x%08x)" % magic)
    if entry_size < 32:
        raise ImgError("dt_table_entry 太小: %d" % entry_size)
    if entry_count > 4096:
        raise ImgError("条目数离谱: %d" % entry_count)
    if entries_offset + entry_count * entry_size > len(data):
        raise ImgError("dt_table 条目越界")

    entries = []
    for i in range(entry_count):
        off = entries_offset + i * entry_size
        dt_size, dt_offset, dt_id, dt_rev = struct.unpack(">4I", data[off:off + 16])
        if dt_offset + dt_size > len(data):
            raise ImgError("第 %d 个 DTB 越界 (off=%d size=%d)" % (i, dt_offset, dt_size))
        entries.append({
            "index": i,
            "size": dt_size,
            "offset": dt_offset,
            "id": dt_id,
            "rev": dt_rev,
            "data": data[dt_offset:dt_offset + dt_size],
        })

    return {
        "kind": "dtbo",
        "total_size": total_size,
        "header_size": header_size,
        "entry_count": entry_count,
        "page_size": page_size,
        "version": version,
        "entries": entries,
    }


# ---------------------------------------------------------------- 统一入口

def parse(path: str) -> dict:
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:8] == BOOT_MAGIC:
        info = parse_boot(data)
    elif data[:8] == VENDOR_MAGIC:
        info = parse_vendor_boot(data)
    else:
        try:
            info = parse_dtbo(data)
        except ImgError:
            raise ImgError("认不出的镜像格式: %s" % path)
    info["file"] = path
    info["file_size"] = len(data)
    return info


def describe(info: dict) -> str:
    lines = ["文件: %s (%d 字节)" % (info["file"], info["file_size"])]
    if info["kind"] == "dtbo":
        lines.append("类型: dtbo (表版本 %s)" % info.get("version", "?"))
    else:
        lines.append("类型: %s (header v%s)" % (info["kind"], info.get("header_version", "?")))

    if info["kind"] == "boot":
        lines.append("内核: %d 字节" % info["kernel_size"])
        lines.append("ramdisk: %d 字节" % info["ramdisk_size"])
        if "signature_size" in info:
            lines.append("boot 签名: %d 字节" % info["signature_size"])
        lines.append("cmdline: %s" % (info["cmdline"] or "(空)"))

    elif info["kind"] == "vendor_boot":
        lines.append("vendor_ramdisk: %d 字节" % info["vendor_ramdisk_size"])
        lines.append("DTB 段: %d 字节 @ %s, 内含 %d 份 FDT" % (
            info["dtb_size"], info["dtb_addr"], len(info["dtbs"])))
        for i, dtb in enumerate(info["dtbs"]):
            lines.append("  #%d  %s" % (i, _fdt_summary(dtb)))
        lines.append("cmdline: %s" % (info["cmdline"] or "(空)"))

    elif info["kind"] == "dtbo":
        lines.append("DTB 条目: %d 个" % info["entry_count"])
        for e in info["entries"]:
            lines.append("  #%d  %8d 字节  id=%d rev=%d  [%s]" % (
                e["index"], e["size"], e["id"], e["rev"], _fdt_summary(e["data"])))

    return "\n".join(lines)


def extract(info: dict, outdir: str) -> list[str]:
    os.makedirs(outdir, exist_ok=True)
    written = []

    def save(name: str, blob: bytes) -> None:
        if not blob:
            return
        path = os.path.join(outdir, name)
        with open(path, "wb") as fh:
            fh.write(blob)
        written.append("%s (%d 字节)" % (path, len(blob)))

    if info["kind"] == "boot":
        save("kernel", info["kernel"])
        save("ramdisk", info["ramdisk"])
    elif info["kind"] == "vendor_boot":
        save("vendor_ramdisk", info["vendor_ramdisk"])
        for i, dtb in enumerate(info["dtbs"]):
            save("vb_dtb_%02d.dtb" % i, dtb)
    elif info["kind"] == "dtbo":
        for e in info["entries"]:
            save("dtbo_%02d_id%d_rev%d.dtb" % (e["index"], e["id"], e["rev"]), e["data"])

    return written


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bootimg", description="安卓引导镜像解析")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_info = sub.add_parser("info", help="查看镜像信息")
    p_info.add_argument("image")

    p_ext = sub.add_parser("extract", help="抽出内核/ramdisk/DTB")
    p_ext.add_argument("image")
    p_ext.add_argument("-o", "--out", default="out")

    args = ap.parse_args(argv)
    try:
        info = parse(args.image)
        if args.cmd == "info":
            print(describe(info))
        else:
            for line in extract(info, args.out):
                print("写出 " + line)
    except (ImgError, OSError) as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
