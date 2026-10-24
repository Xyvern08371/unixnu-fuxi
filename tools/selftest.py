#!/usr/bin/env python3
"""bootimg 自测: 现场合成 boot v4 / vendor_boot v3 / dtbo, 再解析回来。"""
from __future__ import annotations

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "appledt"))

import bootimg as B          # noqa: E402
import apple_dt as A         # noqa: E402
import overlay as O          # noqa: E402
import eficheck as E         # noqa: E402

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def make_fdt() -> bytes:
    root = A.Node("")
    root.set("model", b"fuxi\0")
    mem = root.add("memory")
    mem.set("device_type", b"memory\0")
    return A.serialize(root)


# ---------------------------------------------------------------- 合成样本

def make_boot_v4(kernel: bytes, ramdisk: bytes, cmdline: str = "console=ttyMSM0") -> bytes:
    hdr_size = 1584
    cmd = cmdline.encode()[:1536].ljust(1536, b"\0")
    hdr = (B.BOOT_MAGIC
           + struct.pack("<4I", len(kernel), len(ramdisk), 0, hdr_size)
           + b"\0" * 16
           + struct.pack("<I", 4)
           + cmd
           + struct.pack("<I", 0))          # signature_size
    assert len(hdr) == hdr_size, len(hdr)
    out = bytearray(hdr)
    out += b"\0" * (B.align(hdr_size) - len(out))
    out += kernel
    out += b"\0" * (B.align(len(out)) - len(out))
    out += ramdisk
    out += b"\0" * (B.align(len(out)) - len(out))
    return bytes(out)


def make_vendor_boot(dtb: bytes, vramdisk: bytes = b"VRD") -> bytes:
    hdr_size = 2112
    cmd = b"\0" * 2048
    hdr = (B.VENDOR_MAGIC
           + struct.pack("<I", 3)              # header_version
           + struct.pack("<I", 4096)           # page_size
           + struct.pack("<I", 0)              # kernel_addr
           + struct.pack("<I", 0)              # ramdisk_addr
           + struct.pack("<I", len(vramdisk))  # vendor_ramdisk_size
           + cmd
           + struct.pack("<I", 0)              # tags_addr
           + b"fuxi".ljust(16, b"\0")
           + struct.pack("<I", hdr_size)
           + struct.pack("<I", len(dtb))
           + struct.pack("<Q", 0x10000000))
    assert len(hdr) == hdr_size, len(hdr)
    out = bytearray(hdr)
    out += b"\0" * (B.align(hdr_size) - len(out))
    out += vramdisk
    out += b"\0" * (B.align(len(out)) - len(out))
    out += dtb
    return bytes(out)


def make_dtbo(blobs: list[bytes]) -> bytes:
    # dt_table 是大端! (AOSP mkdtimg 用 cpu_to_fdt32)
    entry_size = 32
    entries_offset = 32
    data_start = B.align(entries_offset + len(blobs) * entry_size)
    entries = b""
    data = bytearray()
    cursor = data_start
    for i, blob in enumerate(blobs):
        entries += struct.pack(">4I", len(blob), cursor, i, 0) + b"\0" * 16
        data += blob
        if i + 1 < len(blobs):
            pad = B.align(cursor + len(blob)) - (cursor + len(blob))
            data += b"\0" * pad
            cursor += len(blob) + pad
        else:
            cursor += len(blob)
    total = data_start + len(data)
    hdr = struct.pack(">8I", B.DTBO_MAGIC, total, 32, entry_size,
                      len(blobs), entries_offset, 4096, 0)
    blob = bytearray(hdr + entries)
    blob += b"\0" * (data_start - len(blob))
    blob += data
    return bytes(blob)


# ---------------------------------------------------------------- 测试

@test
def test_boot_v4():
    kernel, ramdisk = b"K" * 5000, b"R" * 700
    info = B.parse_boot(make_boot_v4(kernel, ramdisk))
    assert info["header_version"] == 4
    assert info["kernel"] == kernel
    assert info["ramdisk"] == ramdisk
    assert info["cmdline"] == "console=ttyMSM0"


@test
def test_vendor_boot():
    dtb = make_fdt()
    info = B.parse_vendor_boot(make_vendor_boot(dtb))
    assert info["header_version"] == 3
    assert info["dtb"] == dtb, "DTB 抽出后内容不一致"
    assert info["vendor_ramdisk"] == b"VRD"
    assert "FDT v17" in B._fdt_summary(info["dtb"])
    assert len(info["dtbs"]) == 1


@test
def test_vendor_boot_multi_fdt():
    a, b = make_fdt(), make_fdt()
    pad = b"\0" * ((len(a) + 3) // 4 * 4 - len(a))
    info = B.parse_vendor_boot(make_vendor_boot(a + pad + b))
    assert len(info["dtbs"]) == 2, "多份 FDT 没切开"
    assert info["dtbs"][0] == a
    assert info["dtbs"][1] == b


@test
def test_dtbo_multi_entry():
    pairs = [make_fdt(), b"\x00" * 64 + make_fdt()[64:]]
    info = B.parse_dtbo(make_dtbo(pairs))
    assert info["entry_count"] == 2
    assert len(info["entries"]) == 2
    assert info["entries"][0]["data"] == pairs[0]
    assert info["entries"][1]["data"] == pairs[1]
    assert info["entries"][1]["id"] == 1


@test
def test_dispatch_by_magic():
    import tempfile
    tmp = os.path.join(HERE, "_selftest_tmp")
    os.makedirs(tmp, exist_ok=True)
    try:
        cases = [("boot.img", make_boot_v4(b"k", b"r")),
                 ("vb.img", make_vendor_boot(make_fdt())),
                 ("dtbo.img", make_dtbo([make_fdt()]))]
        for name, blob in cases:
            path = os.path.join(tmp, name)
            with open(path, "wb") as fh:
                fh.write(blob)
            info = B.parse(path)
            assert info["kind"] in ("boot", "vendor_boot", "dtbo")
            assert info["file_size"] == len(blob)

        out = os.path.join(tmp, "out")
        info = B.parse(os.path.join(tmp, "dtbo.img"))
        written = B.extract(info, out)
        assert len(written) == 1
        with open(os.path.join(out, "dtbo_00_id0_rev0.dtb"), "rb") as fh:
            assert fh.read() == make_fdt(), "抽出的 dtb 内容不对"
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


@test
def test_rejects_bad_input():
    for bad, expect in ((b"NOPE" * 100, B.ImgError),):
        try:
            B.parse_boot(bad)
        except expect:
            pass
        else:
            raise AssertionError("坏 magic 应当抛错")

    # 未知版本要明确拒绝, 而不是解出错数据
    bad = bytearray(make_boot_v4(b"k", b"r"))
    struct.pack_into("<I", bad, 40, 7)
    try:
        B.parse_boot(bytes(bad))
    except B.ImgError as exc:
        assert "7" in str(exc)
    else:
        raise AssertionError("未知版本应当报错")


@test
def test_boot_v1_legacy():
    """Renegade 的 boot-<device>.img 是 v1: 我们要能认出来。"""
    page = 2048
    kernel = b"K" * 3000
    hdr = bytearray(page)
    hdr[0:8] = b"ANDROID!"
    struct.pack_into("<I", hdr, 8, len(kernel))       # kernel_size
    struct.pack_into("<I", hdr, 12, 0x10000000)       # kernel_addr
    struct.pack_into("<I", hdr, 16, 1)                # ramdisk_size = 1 (占位)
    struct.pack_into("<I", hdr, 20, 0x10000000)       # ramdisk_addr
    struct.pack_into("<I", hdr, 36, page)             # page_size
    struct.pack_into("<I", hdr, 40, 1)                # header_version
    struct.pack_into("<I", hdr, 1632, 0)              # recovery_dtbo_size
    struct.pack_into("<I", hdr, 1644, 1648)           # header_size
    blob = bytes(hdr) + kernel + b"\0" * (page - len(kernel) % page if len(kernel) % page else 0)

    info = B.parse_boot(blob)
    assert info["header_version"] == 1
    assert info["page_size"] == page
    assert info["kernel_size"] == len(kernel)
    assert info["kernel"] == kernel, "kernel 抽取位置不对"
    assert info["ramdisk_size"] == 1


# ---------------------------------------------------------------- overlay 合并

def make_base() -> A.Node:
    root = A.Node("")
    soc = root.add("soc")
    soc.set("phandle", struct.pack(">I", 0x10))
    i2c = soc.add("i2c@1000")
    i2c.set("phandle", struct.pack(">I", 0x11))
    i2c.set("compatible", b"qcom,i2c\0")
    sym = root.add("__symbols__")
    sym.set("i2c0", b"/soc/i2c@1000\0")
    return root


def make_overlay() -> A.Node:
    root = A.Node("")
    frag = root.add("fragment@0")
    frag.set("target", struct.pack(">I", 0xFFFFFFFF))
    body = frag.add("__overlay__")
    body.set("status", b"okay\0")
    panel = body.add("panel@0")
    panel.set("phandle", struct.pack(">I", 1))
    panel.set("compatible", b"panel-x\0")
    panel.set("refs", struct.pack(">I", 1))       # 指向 overlay 内的自己

    fx = root.add("__fixups__")
    fx.set("i2c0", b"/fragment@0:target:0\0")

    lf = root.add("__local_fixups__")
    lf_frag = lf.add("fragment@0")
    lf_body = lf_frag.add("__overlay__")
    lf_panel = lf_body.add("panel@0")
    lf_panel.set("refs", struct.pack(">I", 0))
    return root


@test
def test_overlay_apply():
    merged, res = O.apply_overlay(make_base(), make_overlay())
    assert res.fragments_applied == 1, res.fragments_skipped
    assert res.fixups_applied == 1
    assert res.local_patched == 1
    assert res.renumbered == 1

    i2c = merged.find("/soc/i2c@1000")
    assert i2c.get_str("compatible") == "qcom,i2c", "原有属性被破坏"
    assert i2c.get_str("status") == "okay", "overlay 属性没并进来"
    panel = i2c.find("/panel@0")
    # base 最大 phandle 0x11, 新号必须是 0x12
    assert O.node_phandle(panel) == 0x12, hex(O.node_phandle(panel))
    assert O.u32(panel.props["refs"]) == 0x12, "本地引用没重定位"
    assert merged.try_find("/__symbols__") is None, "临时节点没清掉"
    assert O.check(merged) == []


@test
def test_overlay_skips_unknown_target():
    ov = make_overlay()
    base = make_base()
    base.children = [c for c in base.children if c.name != "__symbols__"]
    merged, res = O.apply_overlay(base, ov)
    # 没有 __symbols__ 就解析不出符号, fragment 应被跳过而不是崩
    assert res.fragments_applied == 0
    assert res.fragments_skipped
    assert O.check(merged) == []


# ---------------------------------------------------------------- EFI 检查

def make_efi(machine: int = 0xAA64, subsystem: int = 10, entry: int = 0x1000) -> bytes:
    e_lfanew = 0x80
    size_opt = 0xF0
    blob = bytearray(0x600)
    blob[0:2] = b"MZ"
    struct.pack_into("<I", blob, 0x3C, e_lfanew)
    blob[e_lfanew:e_lfanew + 4] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", blob, e_lfanew + 4,
                     machine, 1, 0, 0, 0, size_opt, 0x22)
    opt = e_lfanew + 24
    struct.pack_into("<H", blob, opt, 0x20B)          # PE32+
    struct.pack_into("<I", blob, opt + 16, entry)     # AddressOfEntryPoint
    struct.pack_into("<H", blob, opt + 68, subsystem) # Subsystem
    sec = opt + size_opt
    blob[sec:sec + 8] = b".text\0\0\0"
    struct.pack_into("<IIII", blob, sec + 8, 0x100, 0x1000, 0x200, 0x400)
    struct.pack_into("<I", blob, sec + 36, 0x60000020)  # code | execute | read
    return bytes(blob)


@test
def test_eficheck_ok():
    info = E.parse(make_efi())
    assert info["machine_name"] == "AArch64"
    assert info["subsystem_name"] == "EFI Application"
    ok, notes = E.verdict(info)
    assert ok, notes


@test
def test_eficheck_rejects():
    ok, notes = E.verdict(E.parse(make_efi(machine=0x8664)))
    assert not ok and any("AArch64" in n for n in notes), notes

    ok, notes = E.verdict(E.parse(make_efi(entry=0x9000)))
    assert not ok, notes

    try:
        E.parse(b"not a pe file" * 10)
    except E.PeError:
        pass
    else:
        raise AssertionError("非 PE 应当抛错")


def main() -> int:
    failed = 0
    for fn in TESTS:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("FAIL  %-24s %s: %s" % (fn.__name__, type(exc).__name__, exc))
        else:
            print("ok    %s" % fn.__name__)
    print("\n%d/%d 通过" % (len(TESTS) - failed, len(TESTS)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
