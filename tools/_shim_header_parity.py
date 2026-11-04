"""让 shim 的 boot.img 头部与能启动的 UEFI 镜像逐字段一致。

差异（UEFI vs 我们）：
  os_version  0x1a00016b  vs  0
  name        空          vs  "fuxi"
  cmdline     空          vs  "console=null"
  second_addr 0           vs  0x10000000
  id          SHA1        vs  全零      ← 最可能被 ABL 校验
"""

import io

M = r"E:\ios-on-fuxi\tools\mkshim_bootimg.py"
t = io.open(M, encoding="utf-8").read()

# 常量
t = t.replace('BOARD_NAME = b"fuxi"', 'BOARD_NAME = b"\\0" * 16   # 空名字（与 UEFI 镜像一致）')
t = t.replace('TAGS_ADDR = 0x10000000',
              'TAGS_ADDR = 0x10000000\nOS_VERSION = 0x1A00016B   # 与 UEFI 镜像一致')
t = t.replace('ap.add_argument("--cmdline", default="console=null")',
              'ap.add_argument("--cmdline", default="")')

# 头部字段：second_addr=0、os_version、id
t = t.replace('''        KERNEL_ADDR,          # second_addr
        TAGS_ADDR,            # tags_addr
        PAGE,                 # page_size
        1,                    # header_version（fuxi 用 v1）
        0,                    # os_version''',
              '''        0,                    # second_addr（与 UEFI 镜像一致）
        TAGS_ADDR,            # tags_addr
        PAGE,                 # page_size
        1,                    # header_version（fuxi 用 v1）
        OS_VERSION,           # os_version''')

# 计算 id（mkbootimg 的做法：sha1(kernel + ramdisk + second)）
if "hashlib" not in t:
    t = t.replace("import struct", "import hashlib\nimport struct")
    t = t.replace('''    hdr = struct.pack(''',
                  '''    sha = hashlib.sha1()
    sha.update(kernel)
    sha.update(ramdisk)
    ident = sha.digest() + b"\\0" * (32 - 20)   # 32 字节，前 20 是 SHA1

    hdr = struct.pack(''')
    t = t.replace('        b"\\0" * 32,           # id', '        ident,                # id = SHA1(kernel+ramdisk)')

io.open(M, "w", encoding="utf-8", newline="\n").write(t)
print("mkshim_bootimg.py: 头部字段已对齐 UEFI 镜像")

for i, line in enumerate(io.open(M, encoding="utf-8").read().split("\n"), 1):
    if any(k in line for k in ("OS_VERSION", "ident", "second_addr", "BOARD_NAME", "cmdline")):
        print("  L%d: %s" % (i, line.rstrip()))
