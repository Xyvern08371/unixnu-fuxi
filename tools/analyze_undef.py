#!/usr/bin/env python3
"""分析链接期的未定义符号：找出它们定义在哪个源文件，以及该文件为什么没被编译。

用法: python3 tools/analyze_undef.py <build.log> <xnu 目录>

输出示例:
    _fillPage  <-  osfmk/arm64/caches_asm.s
        files.arm64 里: osfmk/arm64/caches_asm.s  optional nos_arm_asm
"""

import re
import subprocess
import sys
from pathlib import Path

SEARCH_DIRS = ["osfmk", "bsd", "libkern", "iokit", "pexpert"]


def undefined_symbols(log_path: Path):
    text = log_path.read_text(encoding="utf-8", errors="replace")
    syms = re.findall(r'^\s+"(_\w+)", referenced from:', text, re.M)
    return sorted(set(syms))


def find_definitions(root: Path, name: str, limit: int = 3):
    """在源码树里找这个标识符出现的文件（优先 .s/.c）"""
    try:
        out = subprocess.run(
            ["grep", "-rl", "--include=*.s", "--include=*.c", "--include=*.cpp",
             "--include=*.h", name] + [str(root / d) for d in SEARCH_DIRS],
            capture_output=True, text=True, timeout=60,
        )
    except Exception:            # noqa: BLE001
        return []
    files = [f for f in (out.stdout or "").split("\n") if f.strip()]
    files = [f.replace(str(root) + "/", "") for f in files]
    # 命中最少的优先（更可能是定义处）
    files.sort(key=lambda f: (not f.endswith(".s"), not f.endswith(".c"), len(f)))
    return files[:limit]


def files_entry(root: Path, rel: str):
    """查 files.arm64（或 files）里这个文件的条目"""
    for lst in ("osfmk/conf/files.arm64", "osfmk/conf/files", "bsd/conf/files"):
        p = root / lst
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").split("\n"):
            if line.strip().startswith("#"):
                continue
            if line.split()[:1] and line.split()[0] == rel:
                return f"{lst}: {line.strip()}"
    return "(files 清单里没有这个文件)"


def main() -> int:
    if len(sys.argv) != 3:
        print("用法: analyze_undef.py <build.log> <xnu 目录>")
        return 2
    log_path = Path(sys.argv[1])
    root = Path(sys.argv[2])

    syms = undefined_symbols(log_path)
    print(f"未定义符号总数: {len(syms)}")
    if not syms:
        print("(没有未定义符号 —— 链接可能已经过了)")
        return 0

    seen_files = {}
    for sym in syms:
        name = sym[1:] if sym.startswith("_") else sym
        files = find_definitions(root, name)
        if not files:
            print(f"{sym:45s}  <- (源码里找不到)")
            continue
        for f in files:
            print(f"{sym:45s}  <- {f}")
            seen_files.setdefault(f, 0)
            seen_files[f] += 1

    print()
    print("=" * 70)
    print("按源文件汇总（哪个文件贡献了最多未定义符号）")
    print("=" * 70)
    for f, n in sorted(seen_files.items(), key=lambda kv: -kv[1]):
        print(f"{n:4d}x  {f}")
        print(f"        {files_entry(root, f)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
