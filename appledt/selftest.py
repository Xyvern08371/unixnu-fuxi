#!/usr/bin/env python3
"""apple_dt 自测。无依赖, 直接 python selftest.py"""
from __future__ import annotations

import io
import os
import struct
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import apple_dt as A  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(HERE, "profiles", "fuxi.json")

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def sample_tree() -> A.Node:
    root = A.Node("")
    root.set("#address-cells", struct.pack(">I", 2))
    root.set("model", b"iPhone10,3\0")
    chosen = root.add("chosen")
    chosen.set("boot-args", b"-v keepsyms=1\0")
    chosen.set("dram-base", struct.pack(">Q", 0x80000000))
    mem = root.add("memory")
    mem.set("device_type", b"memory\0")
    # 长度 1/3/5 的属性, 专门用来验证 4 字节对齐
    for i, ln in enumerate((1, 3, 5)):
        mem.set("pad%d" % i, bytes(range(ln)))
    return root


@test
def test_roundtrip():
    root = sample_tree()
    blob = A.serialize(root)
    back = A.parse(blob)
    assert back == root, "往返后结构不一致"


@test
def test_header_sane():
    blob = A.serialize(sample_tree())
    (magic, total, off_struct, off_strings, off_rsv, ver, lastver,
     _cpuid, size_str, size_struct) = struct.unpack(">10I", blob[:40])
    assert magic == A.MAGIC
    assert total == len(blob), "totalsize 与实际长度不符"
    assert ver == 17 and lastver == 16
    assert off_struct % 4 == 0 and off_strings % 4 == 0 and off_rsv % 8 == 0
    assert off_struct + size_struct <= len(blob)
    assert off_strings + size_str == len(blob)
    assert blob[-4:] != b"", "strings 表不应为空"


@test
def test_big_endian():
    root = A.Node("")
    root.set("u32", struct.pack(">I", 0x11223344))
    root.set("u64", struct.pack(">Q", 0x1122334455667788))
    back = A.parse(A.serialize(root))
    assert back.props["u32"] == b"\x11\x22\x33\x44", "u32 不是大端"
    assert back.props["u64"] == bytes.fromhex("1122334455667788"), "u64 不是大端"
    assert back.get_u32("u32") == 0x11223344


@test
def test_property_order():
    root = A.Node("")
    for name in ("z_last", "a_first", "m_mid"):
        root.set(name, b"x\0")
    back = A.parse(A.serialize(root))
    assert list(back.props) == ["z_last", "a_first", "m_mid"], "属性顺序被打乱"


@test
def test_padding_robust():
    root = A.Node("")
    for i, ln in enumerate((0, 1, 2, 3, 4, 5, 7, 9)):
        root.set("p%d" % i, bytes(range(ln)))
    back = A.parse(A.serialize(root))
    for i, ln in enumerate((0, 1, 2, 3, 4, 5, 7, 9)):
        assert back.props["p%d" % i] == bytes(range(ln)), "长度 %d 的属性损坏" % ln


@test
def test_string_table_dedup():
    root = A.Node("")
    for i in range(5):
        child = root.add("n%d" % i)
        child.set("compatible", b"x\0")
    blob = A.serialize(root)
    assert blob.count(b"compatible\0") == 1, "字符串表没有去重"


@test
def test_nested_and_lookup():
    root = sample_tree()
    back = A.parse(A.serialize(root))
    assert back.find("/chosen").get_str("boot-args") == "-v keepsyms=1"
    assert back.find("/memory").get_u32("missing-prop") is None
    assert back.try_find("/nope") is None
    try:
        back.find("/nope")
    except A.DtError:
        pass
    else:
        raise AssertionError("不存在的路径应当抛错")


@test
def test_reject_bad_input():
    try:
        A.parse(b"")
    except A.DtError:
        pass
    else:
        raise AssertionError("空输入应当抛错")

    bad = bytearray(A.serialize(sample_tree()))
    bad[0:4] = b"\xde\xad\xbe\xef"
    try:
        A.parse(bytes(bad))
    except A.DtError:
        pass
    else:
        raise AssertionError("magic 错误应当抛错")

    good = A.serialize(sample_tree())
    try:
        A.parse(good[:len(good) // 2])
    except A.DtError:
        pass
    else:
        raise AssertionError("截断的 blob 应当抛错")


@test
def test_deterministic():
    root = sample_tree()
    assert A.serialize(root) == A.serialize(root), "同一棵树两次序列化结果不同"


@test
def test_profile_synth():
    root = A.build(A.load_profile(PROFILE))
    assert root.name == ""
    chosen = root.find("/chosen")
    assert chosen.get_str("boot-args").startswith("-v"), "boot-args 没写进去"
    assert chosen.props["dram-base"] == struct.pack(">Q", 0x80000000)
    product = root.find("/product")
    assert product.get_str("model") == "iPhone10,3"
    assert len(root.find("/cpus").children) == 8, "cpus 子节点数不对"

    blob = A.serialize(root)
    back = A.parse(blob)
    assert back == root
    assert back.find("/arm-io/uart0").props["reg"] == struct.pack(">QQ", 0xA9C000, 0x4000)
    gic = back.find("/arm-io/gic")
    assert gic.get_str("compatible") == "arm,gic-v3"
    assert "interrupt-controller" in gic.props


@test
def test_cli_end_to_end():
    # 注意: 不用 tempfile —— 沙箱对 tmp* 命名的目录有限制, 这里用固定目录
    tmp = os.path.join(HERE, "_selftest_tmp")
    os.makedirs(tmp, exist_ok=True)
    try:
        dtb = os.path.join(tmp, "fuxi.dtb")
        dtb2 = os.path.join(tmp, "again.dtb")

        assert A.main(["synth", PROFILE, "-o", dtb]) == 0
        assert os.path.getsize(dtb) > 256

        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            assert A.main(["dump", dtb]) == 0
        finally:
            sys.stdout = old
        text = buf.getvalue()
        assert "chosen {" in text and "boot-args" in text, "dump 输出不完整"
        assert "iPhone10,3" in text

        assert A.main(["from-fdt", dtb, "-o", dtb2]) == 0
        with open(dtb, "rb") as f1, open(dtb2, "rb") as f2:
            assert f1.read() == f2.read(), "from-fdt 往返后字节不一致"

        assert A.main(["synth", os.path.join(tmp, "missing.json"), "-o", dtb]) == 1
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    failed = 0
    for fn in TESTS:
        name = fn.__name__
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("FAIL  %-26s %s: %s" % (name, type(exc).__name__, exc))
        else:
            print("ok    %s" % name)
    total = len(TESTS)
    print("\n%d/%d 通过" % (total - failed, total))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
