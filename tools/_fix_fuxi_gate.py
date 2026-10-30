"""把补丁里的 `#if defined(FUXI)` 改成 `#if defined(ARM64_BOARD_CONFIG_FUXI)`。

编译日志确认：构建只传 -DARM64_BOARD_CONFIG_FUXI（1042 次），从来没有 -DFUXI。
所以所有 `#if defined(FUXI)` 的门控全部为假，我们的替换代码根本没编进去，
跑的是 Apple 原始实现 —— 在 fuxi 上访问到不存在的地址就 panic。
"""

import glob
import io

OLD = "defined(FUXI)"
NEW = "defined(ARM64_BOARD_CONFIG_FUXI)"

total = 0
for f in sorted(glob.glob(r"E:\ios-on-fuxi\xnu\patches\*.patch")):
    t = io.open(f, encoding="utf-8").read()
    n = t.count(OLD)
    if n:
        t = t.replace(OLD, NEW)
        io.open(f, "w", encoding="utf-8", newline="\n").write(t)
        print(f"  {f.split(chr(92))[-1]}: {n} 处")
        total += n

print(f"\n合计 {total} 处门控修正")

# 检查有没有漏（比如 defined(FUXI) 的变体）
for f in sorted(glob.glob(r"E:\ios-on-fuxi\xnu\patches\*.patch")):
    for i, line in enumerate(io.open(f, encoding="utf-8").read().split("\n"), 1):
        if "defined(FUXI" in line and "ARM64_BOARD_CONFIG" not in line:
            print(f"  ⚠ 残留 {f.split(chr(92))[-1]}:{i}: {line.strip()}")
