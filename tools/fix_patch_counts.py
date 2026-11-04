"""重新计算 patch 文件里每个 hunk 的行数（手工改过 hunk 内容后必需）。

unified diff 的 @@ -start,old +start,new @@ 计数必须和实际行数一致，
否则 git apply 会报 "corrupt patch"。这个脚本会重算。
"""

import io
import re
import sys

P = sys.argv[1] if len(sys.argv) > 1 else r"E:\ios-on-fuxi\xnu\patches\0004-fuxi-machine-config.patch"

lines = io.open(P, encoding="utf-8").read().split("\n")
out = []
i = 0
fixed = 0

while i < len(lines):
    line = lines[i]
    m = re.match(r"^@@ -(\d+),(\d+) \+(\d+),(\d+) @@(.*)$", line)
    if not m:
        out.append(line)
        i += 1
        continue

    old_start = int(m.group(1))
    new_start = int(m.group(3))
    tail = m.group(5)

    # 收集 hunk 主体
    j = i + 1
    body = []
    while j < len(lines):
        l = lines[j]
        if l.startswith("@@") or l.startswith("diff --git ") or l.startswith("--- ") or l.startswith("+++ "):
            break
        body.append(l)
        j += 1

    old_count = sum(1 for l in body if l[:1] == " " or l[:1] == "-")
    new_count = sum(1 for l in body if l[:1] == " " or l[:1] == "+")

    new_header = f"@@ -{old_start},{old_count} +{new_start},{new_count} @@{tail}"
    if new_header != line:
        fixed += 1
    out.append(new_header)
    out.extend(body)
    i = j

io.open(P, "w", encoding="utf-8", newline="\n").write("\n".join(out))
print(f"重算完成，修正 {fixed} 个 hunk 头")
