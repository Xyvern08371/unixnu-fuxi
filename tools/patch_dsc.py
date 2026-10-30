#!/usr/bin/env python3
"""patch_dsc.py -- 把一条组件路径插进 DSC 的 [Components] 段

为什么不用 sed: 用 sed 写
    s/^\\[Components/s//&\\n  xxx/
时, & 只等于 "[Components"（不含结尾的 ]），插入后会变成
    [Components
      xxx]
段头丢掉 ]，解析器直接报 error 3000。这个坑踩过一次, 所以改成 Python。

用法:
  python patch_dsc.py <dsc文件> <组件路径>
  已存在则不重复插入, 返回 0 并提示。
"""
from __future__ import annotations

import re
import sys

HEADER_RE = re.compile(r"^\s*\[Components[^\]]*\]", re.IGNORECASE)


def add_component(path: str, component: str) -> tuple[bool, str]:
    with open(path, "r", encoding="utf-8-sig") as fh:
        text = fh.read()

    if component in text:
        return True, "已存在，跳过"

    lines = text.splitlines()
    for i, line in enumerate(lines):
        if HEADER_RE.match(line):
            lines.insert(i + 1, "  " + component)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("\n".join(lines) + "\n")
            return True, "插到第 %d 行之后" % (i + 1)

    return False, "这个文件里没有 [Components] 段"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("用法: python patch_dsc.py <dsc> <component>", file=sys.stderr)
        return 2
    path, component = argv
    try:
        ok, msg = add_component(path, component)
    except OSError as exc:
        print("读不了 %s: %s" % (path, exc), file=sys.stderr)
        return 1
    print("%s: %s" % (path, msg))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
