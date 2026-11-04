"""去掉固件工作流的 workflow_run 触发器，并加 concurrency（按行处理，稳妥）。"""

import io

FW = r"E:\ios-on-fuxi\.github\workflows\build-fuxi-uefi.yml"
lines = io.open(FW, encoding="utf-8").read().split("\n")

# 1) 删除 workflow_run 块（从 '  workflow_run:' 到下一个同级 key）
out = []
i = 0
removed = 0
while i < len(lines):
    ln = lines[i]
    if ln.strip() == "workflow_run:" and ln.startswith("  ") and not ln.startswith("    "):
        i += 1
        while i < len(lines) and (lines[i].startswith("    ") or lines[i].strip() == ""):
            i += 1
        removed += 1
        continue
    out.append(ln)
    i += 1
print("删除 workflow_run 块:", removed)

# 2) 删掉紧邻的那条中文注释（说明 workflow_run 的）
out2 = []
for idx, ln in enumerate(out):
    if "xnu" in ln and "workflow_run" in ln and ln.strip().startswith("#"):
        continue
    out2.append(ln)
out = out2

# 3) 在顶层 on: 之前插入 concurrency
if not any(l.startswith("concurrency:") for l in out):
    pos = next(i for i, l in enumerate(out) if l.strip() == "on:" and not l.startswith(" "))
    out[pos:pos] = [
        "concurrency:",
        "  group: fuxi-uefi-${{ github.ref }}",
        "  cancel-in-progress: true",
        "",
    ]
    print("已插入 concurrency")

io.open(FW, "w", encoding="utf-8", newline="\n").write("\n".join(out))
print("写回完成")

s = io.open(FW, encoding="utf-8").read()
print("还有 workflow_run:", "workflow_run:" in s)
print("有 concurrency:", "concurrency:" in s)
