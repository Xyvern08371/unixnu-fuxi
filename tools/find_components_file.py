#!/usr/bin/env python3
"""find_components_file.py -- 找出 edk2 DSC 里真正定义 [Components] 的文件

背景: fuxi.dsc 本身没有 [Components], 它 !include 了 Platform/Qualcomm/sm8550/sm8550.dsc,
再层层 include。往错的文件里插 INF, build 会报 F001 "NOT found in DSC"。
所以要先沿着 include 链找到真正含 [Components 的那个文件。

用法:
  python find_components_file.py <repo_root> <起始.dsc>
  输出: 文件路径（找不到则输出空并返回 1）
"""
from __future__ import annotations

import os
import re
import sys

INCLUDE_RE = re.compile(r"^\s*!include\s+(.+?)\s*$", re.MULTILINE)
COMPONENTS_RE = re.compile(r"^\s*\[Components", re.MULTILINE | re.IGNORECASE)


def _read(path: str) -> str:
    try:
        # utf-8-sig: 顺带吃掉 BOM, 否则首行的 !include 匹配不到
        with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def _resolve(root: str, including_file: str, target: str) -> str | None:
    """!include 的路径一般相对仓库根; 也有相对当前文件的写法, 两种都试。"""
    cands = [
        os.path.normpath(os.path.join(root, target)),
        os.path.normpath(os.path.join(os.path.dirname(including_file), target)),
    ]
    for c in cands:
        if os.path.exists(c):
            return c
    return None


def find(root: str, start: str, seen: set[str] | None = None) -> str | None:
    seen = seen if seen is not None else set()
    start = os.path.normpath(start)
    if start in seen or not os.path.exists(start):
        return None
    seen.add(start)

    text = _read(start)
    if COMPONENTS_RE.search(text):
        return start

    for target in INCLUDE_RE.findall(text):
        inc = _resolve(root, start, target.strip())
        if inc is None:
            continue
        hit = find(root, inc, seen)
        if hit is not None:
            return hit
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("用法: python find_components_file.py <repo_root> <start.dsc>", file=sys.stderr)
        return 2
    root, start = argv
    hit = find(root, start)
    if hit is None:
        print("没找到含 [Components 的 DSC/inc", file=sys.stderr)
        return 1
    print(hit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
