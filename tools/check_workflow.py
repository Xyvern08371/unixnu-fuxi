#!/usr/bin/env python3
"""check_workflow.py -- GitHub Actions 工作流的粗检查

只查最容易犯、又最难在本地发现的两类错:
  1. 制表符(TAB) —— YAML 不允许
  2. 顶格出现的非顶层键行 —— 典型是 heredoc 的 EOF 忘了缩进,
     会把 `run: |` 块截断, GitHub 直接判 workflow 非法(1 秒失败)

用法: python check_workflow.py .github/workflows/build-fuxi-uefi.yml
"""
from __future__ import annotations

import sys

TOP_LEVEL = ("name:", "on:", "jobs:", "#", "---", "run-name:", "permissions:",
             "env:", "concurrency:", "defaults:")


def check(path: str) -> list[str]:
    problems = []
    with open(path, "r", encoding="utf-8") as fh:
        lines = fh.read().split("\n")

    for no, line in enumerate(lines, 1):
        if "\t" in line:
            problems.append("行 %d: 含 TAB（YAML 不允许）" % no)
        if not line or line.startswith(" ") or line.startswith("#"):
            continue
        if line.strip() == "":
            continue
        if any(line.startswith(k) for k in TOP_LEVEL):
            continue
        problems.append("行 %d: 顶格出现 [%s] —— 可能截断了 run: | 块" % (no, line[:40]))

    # heredoc 结束符必须和内容同缩进
    for no, line in enumerate(lines, 1):
        if line.strip().upper() in ("EOF", "END") and line == line.strip():
            problems.append("行 %d: heredoc 结束符顶格，应缩进到与内容一致" % no)

    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("用法: python check_workflow.py <workflow.yml>", file=sys.stderr)
        return 2
    problems = check(argv[0])
    if problems:
        print("发现 %d 个问题:" % len(problems))
        for p in problems:
            print("  " + p)
        return 1
    print("OK: %s 未发现明显问题" % argv[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
