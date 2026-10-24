#!/usr/bin/env python3
"""把 XNU payload 作为 RAW section 插进 FDF 的 [FV.FvMain]。

用法: add_fv_payload.py <fdf> <payload 相对路径> [guid]

为什么不用 sed：多行插入 + FDF 的 # 注释会让 `SECTION RAW` 被注释掉，
之前那次构建就是因此失败的。
"""

import io
import sys

GUID = "9f3c7a21-5b4e-4c8d-9a11-7e2b6308d451"
MARK = "XNU PAYLOAD"


def main() -> int:
    if len(sys.argv) < 3:
        print("用法: add_fv_payload.py <fdf> <payload 相对路径> [guid]")
        return 2

    fdf_path, payload_rel = sys.argv[1], sys.argv[2]
    guid = sys.argv[3] if len(sys.argv) > 3 else GUID

    text = io.open(fdf_path, encoding="utf-8", errors="replace").read()
    if MARK in text:
        print("FDF 里已经有 XNU PAYLOAD，跳过")
        return 0

    block = (
        "\n"
        "# XNU PAYLOAD: XNU 内核镜像（RAW section，不是可执行模块）\n"
        f"FILE FREEFORM = {guid} {{\n"
        f"  SECTION RAW = {payload_rel}\n"
        "}\n"
    )

    # 插到探针 INF 那一行之后
    anchor = "INF Platform/Xiaomi/sm8550/probe/Probe.inf"
    idx = text.find(anchor)
    if idx < 0:
        print("!! FDF 里找不到探针 INF 行")
        return 1

    eol = text.find("\n", idx)
    if eol < 0:
        eol = len(text)
    new = text[:eol + 1] + block + text[eol + 1:]

    io.open(fdf_path, "w", encoding="utf-8", newline="\n").write(new)
    print(f"已在 FDF 插入 RAW section（{payload_rel}）")
    print(new[eol - 100:eol + len(block) + 20])
    return 0


if __name__ == "__main__":
    sys.exit(main())
