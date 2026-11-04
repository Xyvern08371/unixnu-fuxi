

import io

p = r"E:\ios-on-fuxi\fuxi-unixnu\scripts\make-fuxi-adt.py"
t = io.open(p, encoding="utf-8").read()

# 1) 在 chosen 节点之后插入 pram 节点
i = t.find("node('chosen'")
assert i > 0
depth = 0
j = i
while j < len(t):
    if t[j] == "[":
        depth += 1
    elif t[j] == "]":
        depth -= 1
        if depth == 0:
            j += 2
            break
    j += 1

insert = """
        # XNU 的 pe_init.c:check_for_panic_log() 读 /pram 的 reg[0]（物理地址）
        # 和 /chosen 的 embedded-panic-log-size（可写大小），两者齐备才设
        # gPanicBase。缺了它 debug_log_init 会报 gPanicBase 未初始化，
        # panic 日志无处可写（debug_buf_base 落在 NULL 附近）。
        node('pram',
             [('reg', struct.pack('<QQ', args.panic_region, PANIC_LOG_SIZE))]),
"""
if "node('pram'" not in t:
    t = t[:j] + insert + t[j:]

# 2) 加 --panic-region 参数
marker = "    ap.add_argument('--trust-cache'"
if "--panic-region" not in t:
    idx = t.find(marker)
    assert idx > 0, "找不到 --trust-cache 参数"
    arg = (
        "    ap.add_argument('--panic-region', type=lambda s: int(s, 0), default=0,\n"
        "                    help='panic log 区物理地址（512KB，需在 DRAM 窗口内且不与内核重叠）')\n"
    )
    t = t[:idx] + arg + t[idx:]

io.open(p, "w", encoding="utf-8", newline="\n").write(t)
print("已插入 pram 节点和 --panic-region 参数")

import ast
ast.parse(io.open(p, encoding="utf-8").read())
print("语法 OK")
