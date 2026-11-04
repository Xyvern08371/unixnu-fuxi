#!/usr/bin/env python3
"""让 osfmk/arm64/start.s 参与编译（只改构建清单，不动业务代码）。

问题链:
  链接报 `entry point (__start) undefined`
  → start.s 没被汇编 → 没有 start.o
  → osfmk/conf/files.arm64 里这一行是:
        osfmk/arm64/start.s   optional  nos_arm_asm
    `nos_arm_asm` 这个 tag 在当前构建里不成立，于是文件被排除

关键观察（来自 CI 导出的 files.arm64 前 40 行）:
  同一批 arm64 汇编里，绝大多数是 `standard`（无条件编译）:
        osfmk/arm64/bcopy.s            standard
        osfmk/arm64/bzero.s            standard
        osfmk/arm64/lz4_decode_arm64.s standard
  只有 start.s（以及 caches_asm.s 等少数）带 `optional ...`。
  而 `arm64` 并不是这个构建系统认识的 tag（试过 `optional arm64`，仍被排除）。
  所以正确写法是把它改成 `standard`，和 bcopy.s 保持一致。

用法: python3 xnu-stubs/patch_files_arm64.py <xnu 目录>
"""

import re
import sys
from pathlib import Path

LIST_FILES = ["osfmk/conf/files.arm64", "osfmk/conf/files"]


def patch_one(root: Path, list_path: Path) -> int:
    if not list_path.exists():
        print(f"跳过（不存在）: {list_path}")
        return 0

    lines = list_path.read_text(encoding="utf-8", errors="replace").split("\n")
    changed = 0

    for i, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            continue
        # 放开所有带 nos_* 门控的条目（nos_arm_asm / nos_arm_pmap 等），
        # 前提是源文件在开源树里真实存在。
        if "nos_" not in line:
            continue

        parts = line.split()
        if not parts:
            continue
        src_rel = parts[0]

        if not (root / src_rel).exists():
            print(f"跳过（源码不存在）: {src_rel}")
            continue


        new = f"{src_rel}\tstandard"
        if new != line:
            print(f"第 {i + 1} 行: {line}")
            print(f"     -> : {new}")
            lines[i] = new
            changed += 1

    if changed:
        list_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"{list_path}: 修改 {changed} 行")
    return changed


def main() -> int:
    if len(sys.argv) != 2:
        print("用法: patch_files_arm64.py <xnu 目录>")
        return 2
    root = Path(sys.argv[1])
    if not root.is_dir():
        print(f"目录不存在: {root}")
        return 2

    total = 0
    for rel in LIST_FILES:
        total += patch_one(root, root / rel)

    print()
    print(f"共修改 {total} 行")
    if total == 0:
        print("警告: 没有修改任何行，需要人工确认 files.arm64")
    return 0


if __name__ == "__main__":
    sys.exit(main())
