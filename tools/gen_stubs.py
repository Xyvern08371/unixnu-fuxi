#!/usr/bin/env python3
"""根据链接日志里的未定义符号，生成 C 空实现源码。

用法: python3 tools/gen_stubs.py <pass2.log> <输出.c>

背景:
  开源 XNU 缺一批 Apple 私有实现（KPC 性能计数器、DART IOMMU 等）。
  为了先让链接通过，这里为每个未定义符号生成一个空实现。

注意:
  这些是**空实现**，运行时遇到它们会崩溃。它们只是为了先拿到 kernel.release，
  之后必须逐个替换成真正的实现（或者把对应子系统关掉）。
"""

import re
import sys
from pathlib import Path

# 已知是数据的符号（用数组定义，避免被当成函数）
DATA_HINTS = (
    "table", "count", "max", "min", "config", "state", "lock", "list",
    "_pmap", "phys", "size", "flag", "rgns", "kvtophys",
)


def symbols(log_path: Path):
    text = log_path.read_text(encoding="utf-8", errors="replace")
    return sorted(set(re.findall(r'^\s+"(_\w+)", referenced from:', text, re.M)))


def main() -> int:
    if len(sys.argv) != 3:
        print("用法: gen_stubs.py <pass2.log> <输出.c>")
        return 2
    log_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])

    if not log_path.exists():
        print(f"{log_path} 不存在")
        return 1

    syms = symbols(log_path)
    if not syms:
        print("没有未定义符号，无需生成")
        out_path.write_text("/* 无需空实现 */\n", encoding="utf-8")
        return 0

    lines = [
        "/*",
        " * 自动生成的空实现（fuxi）",
        f" * 共 {len(syms)} 个符号，来自 pass2.log 的未定义列表。",
        " *",
        " * 这些是 Apple 私有实现（KPC / DART 等）的占位，运行时不可用。",
        " * 目的是先让链接通过、拿到 kernel.release。",
        " */",
        "",
        "#include <sys/types.h>",
        "",
    ]

    funcs = 0
    datas = 0
    for s in syms:
        name = s[1:] if s.startswith("_") else s
        is_data = any(h in name.lower() for h in DATA_HINTS)
        if is_data:
            lines.append(f"char {name}[16] = {{0}};   /* 数据占位 */")
            datas += 1
        else:
            lines.append(f"void {name}(void) {{ }}   /* 函数占位 */")
            funcs += 1
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"已生成 {out_path}：{len(syms)} 个符号（函数 {funcs} / 数据 {datas}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
