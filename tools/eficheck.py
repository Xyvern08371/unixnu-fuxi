#!/usr/bin/env python3
"""eficheck.py -- 检查一个 .efi 是不是货真价实的 UEFI 应用

用途: 从 Actions 下载的 FuxiLoader.efi, 或网上任何一个 .efi, 刷进手机前先验。
不验就刷, 等于拿设备赌别人的文件名。

检查项:
  1. DOS 头 / PE 签名
  2. 机器类型 (AArch64 = 0xAA64, 别的架构刷到 fuxi 上直接不启动)
  3. 子系统 (10 = EFI 应用, 11/12 = 驱动)
  4. 入口点是否落在某个可执行段里
  5. 段表是否越界

用法:
  python eficheck.py FuxiLoader.efi
"""
from __future__ import annotations

import hashlib
import struct
import sys

MACHINES = {
    0xAA64: "AArch64",
    0x8664: "x86-64",
    0x014C: "i386",
    0x01C0: "ARM",
    0x01C4: "ARMv7 (Thumb-2)",
}

SUBSYSTEMS = {
    10: "EFI Application",
    11: "EFI Boot Service Driver",
    12: "EFI Runtime Driver",
    13: "EFI ROM",
    14: "XBOX",
    1: "Native",
    3: "Windows CUI",
}

SC_CNT_CODE = 0x00000020
SC_MEM_EXECUTE = 0x20000000


class PeError(ValueError):
    pass


def parse(blob: bytes) -> dict:
    if len(blob) < 0x40 or blob[:2] != b"MZ":
        raise PeError("没有 MZ 头，可能不是 PE 文件（zip 没解压？）")

    e_lfanew, = struct.unpack_from("<I", blob, 0x3C)
    if e_lfanew + 24 > len(blob):
        raise PeError("e_lfanew 越界: 0x%x" % e_lfanew)
    if blob[e_lfanew:e_lfanew + 4] != b"PE\0\0":
        raise PeError("没有 PE 签名（不是 PE/COFF）")

    coff = e_lfanew + 4
    machine, nsect, _ts, _psym, _nsym, size_opt, chars = struct.unpack_from(
        "<HHIIIHH", blob, coff)

    opt = coff + 20
    if size_opt < 70:
        raise PeError("可选头太小: %d" % size_opt)
    magic, = struct.unpack_from("<H", blob, opt)
    if magic not in (0x10B, 0x20B):
        raise PeError("可选头 magic 不对: 0x%x" % magic)
    entry, = struct.unpack_from("<I", blob, opt + 16)
    subsystem, = struct.unpack_from("<H", blob, opt + 68)

    sections = []
    sec = opt + size_opt
    for i in range(nsect):
        off = sec + i * 40
        if off + 40 > len(blob):
            raise PeError("段表越界 at %d" % i)
        name = blob[off:off + 8].rstrip(b"\0").decode("ascii", "replace")
        vsize, vaddr, rawsize, rawptr = struct.unpack_from("<IIII", blob, off + 8)
        sc, = struct.unpack_from("<I", blob, off + 36)
        if rawptr + rawsize > len(blob):
            raise PeError("段 %s 的原始数据越界 (rawptr=0x%x rawsize=0x%x, 文件 %d 字节)"
                          % (name, rawptr, rawsize, len(blob)))
        sections.append({
            "name": name, "vsize": vsize, "vaddr": vaddr,
            "rawsize": rawsize, "rawptr": rawptr, "chars": sc,
            "exec": bool(sc & (SC_CNT_CODE | SC_MEM_EXECUTE)),
        })

    return {
        "format": "PE32+" if magic == 0x20B else "PE32",
        "machine": machine,
        "machine_name": MACHINES.get(machine, "未知(0x%x)" % machine),
        "sections": nsect,
        "subsystem": subsystem,
        "subsystem_name": SUBSYSTEMS.get(subsystem, "未知(%d)" % subsystem),
        "entry": entry,
        "chars": chars,
        "section_table": sections,
        "size": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
    }


def verdict(info: dict) -> tuple[bool, list[str]]:
    notes = []
    ok = True

    if info["machine"] != 0xAA64:
        ok = False
        notes.append("架构是 %s，不是 AArch64 —— 刷到 fuxi 上不会启动" % info["machine_name"])
    if info["format"] != "PE32+":
        ok = False
        notes.append("不是 PE32+（64 位），AArch64 的 EFI 必须是 PE32+")
    if info["subsystem"] != 10:
        notes.append("子系统是 %s，不是 EFI Application（可能不是给 UEFI shell 直接跑的）"
                     % info["subsystem_name"])

    hit = [s for s in info["section_table"]
           if s["vaddr"] <= info["entry"] < s["vaddr"] + max(s["vsize"], s["rawsize"])]
    if not hit:
        ok = False
        notes.append("入口点 0x%x 不在任何段里" % info["entry"])
    elif not hit[0]["exec"]:
        notes.append("入口点落在非可执行段 %s" % hit[0]["name"])

    if ok and not notes:
        notes.append("看起来是一个正常的 AArch64 UEFI 应用")
    return ok, notes


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("用法: python eficheck.py <file.efi>", file=sys.stderr)
        return 2
    path = argv[0]
    try:
        with open(path, "rb") as fh:
            blob = fh.read()
    except OSError as exc:
        print("打不开 %s: %s" % (path, exc), file=sys.stderr)
        return 1

    try:
        info = parse(blob)
    except PeError as exc:
        print("不是有效的 PE 文件: %s" % exc, file=sys.stderr)
        return 1

    print("文件   : %s (%d 字节)" % (path, info["size"]))
    print("格式   : %s / %s" % (info["format"], info["machine_name"]))
    print("子系统 : %s" % info["subsystem_name"])
    print("入口点 : RVA 0x%x" % info["entry"])
    print("段 (%d):" % info["sections"])
    for s in info["section_table"]:
        print("  %-8s vaddr=0x%-8x vsize=%-8d raw=%-8d %s"
              % (s["name"], s["vaddr"], s["vsize"], s["rawsize"],
                 "可执行" if s["exec"] else ""))
    print("sha256 : %s" % info["sha256"])

    ok, notes = verdict(info)
    print()
    print("结论: %s" % ("通过" if ok else "有问题"))
    for n in notes:
        print("  - %s" % n)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
