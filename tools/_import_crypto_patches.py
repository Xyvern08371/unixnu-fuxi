"""导入 ios-sweet 的加密算法补丁（BearSSL: MD5/SHA1/SHA256/SHA384-512 + AES）。

我们的内核在 generatePlatformUUID 里崩，因为 sha1_init 是空壳 —— 这些实现
来自 BearSSL，由 0020-stage-bearssl.sh 在构建时拉源码并编译。

做法：
  · 补丁内容原样保留（内部函数名 sweet_* 不动，避免破坏引用）
  · 只把 staging 脚本里的 MACHINE_CONFIG 门控从 SWEET 改成 FUXI
  · 重新编号，插到我们现有序列之后（0022..0027）
"""

import io
import shutil
from pathlib import Path

SRC = Path(r"E:\download\ios-sweet\xnu\patches")
DST = Path(r"E:\ios-on-fuxi\xnu\patches")

# (源文件名, 新文件名)
IMPORT = [
    ("0020-stage-bearssl.sh",                      "0022-stage-bearssl.sh"),
    ("0020-sweet-portable-aes-cbc.patch",          "0022-fuxi-portable-aes-cbc.patch"),
    ("0023-sweet-builtin-sha256-for-libkern.patch", "0023-fuxi-builtin-sha256.patch"),
    ("0027-sweet-bearssl-md5.patch",               "0024-fuxi-bearssl-md5.patch"),
    ("0032-sweet-bearssl-sha1.patch",              "0025-fuxi-bearssl-sha1.patch"),
    ("0033-sweet-bearssl-sha384-sha512.patch",     "0026-fuxi-bearssl-sha384-512.patch"),
]

for src_name, dst_name in IMPORT:
    src = SRC / src_name
    if not src.exists():
        print(f"!! 源文件不存在: {src_name}")
        continue
    text = src.read_text(encoding="utf-8", errors="replace")

    if dst_name.endswith(".sh"):
        # 只改门控，其余原样（脚本里大量 sweet_ 路径必须保持不变）
        before = text
        text = text.replace('== SWEET ]]', '== FUXI ]]')
        text = text.replace('"SWEET"', '"FUXI"')
        changed = text != before
        print(f"{dst_name}: 门控 SWEET->FUXI {'已改' if changed else '未找到门控'}")
    else:
        print(f"{dst_name}: 原样导入（{len(text)} 字节）")

    (DST / dst_name).write_text(text, encoding="utf-8", newline="\n")

print("\n现在的补丁序列:")
for f in sorted(DST.iterdir()):
    if f.suffix in (".patch", ".sh"):
        print("  ", f.name)
