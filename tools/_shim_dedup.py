"""去掉 build-shim.sh 里重复的 payload 内嵌块（保留 ls -l 之后的那段删除）。"""

import io

B = r"E:\ios-on-fuxi\loader-shim-fuxi\build-shim.sh"
t = io.open(B, encoding="utf-8").read()

marker = 'ls -l "$OUT/Image"'
i = t.find(marker)
assert i > 0

tail_start = i + len(marker)
end_marker = 'echo "=== shim 编译完成 ==="'
j = t.find(end_marker, tail_start)
assert j > 0

# 保留 ls -l 之后到 end_marker 之间的空行，删掉重复的 payload 块
t = t[:tail_start] + "\n\n" + t[j:]
io.open(B, "w", encoding="utf-8", newline="\n").write(t)
print("已去掉重复块")
print("----- 结果 -----")
print(io.open(B, encoding="utf-8").read())
