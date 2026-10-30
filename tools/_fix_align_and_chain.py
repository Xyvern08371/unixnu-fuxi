"""1) 内核内存 32MB 对齐；2) xnu 构建完成后自动触发固件构建。"""

import io

# ---------- 1) XnuMem：分配后向上对齐到 32MB ----------
P = r"E:\ios-on-fuxi\loader\XnuMem.c"
t = io.open(P, encoding="utf-8").read()

old = """  mXnuPhysBase = (UINT64)Pages;"""
new = """  /*
   * XNU 的 start.s 用 32MB 块描述符建映射，physBase 必须 32MB 对齐，
   * 否则块边界和 virtBase 对不上，一开 MMU 就崩（实测症状：没有蓝带）。
   */
  mXnuPhysBase = ((UINT64)Pages + 0x1FFFFFFULL) & ~0x1FFFFFFULL;"""
assert old in t, "alloc 锚点没找到"
t = t.replace(old, new, 1)

# 申请时多要 32MB，保证对齐后仍够用
t = t.replace(
    "  Want = NEED_BYTES / EFI_PAGE_SIZE;",
    "  Want = (NEED_BYTES + 0x2000000ULL) / EFI_PAGE_SIZE;",
)
io.open(P, "w", encoding="utf-8", newline="\n").write(t)
print("XnuMem.c: physBase 已改成 32MB 对齐")

# ---------- 2) 固件 workflow：xnu 构建完成后自动跑 ----------
W = r"E:\ios-on-fuxi\.github\workflows\build-fuxi-uefi.yml"
w = io.open(W, encoding="utf-8").read()
if "workflow_run" not in w:
    old_on = """on:
  push:
    paths:"""
    new_on = """on:
  # xnu 内核构建完成后自动重编固件（省掉一次人工等待）
  workflow_run:
    workflows: ["build-xnu"]
    types: [completed]
  push:
    paths:"""
    assert old_on in w
    w = w.replace(old_on, new_on, 1)
    io.open(W, "w", encoding="utf-8", newline="\n").write(w)
    print("固件 workflow: 已加 workflow_run 自动触发")

lines = w.split("\n")
bad = [i for i, l in enumerate(lines, 1) if not l.strip().startswith("#") and l.count('"') % 2]
print("引号不配对:", bad[:5] if bad else "无")
