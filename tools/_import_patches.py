import io
import re
import shutil
from pathlib import Path

SRC = Path(r"E:\download\ios-sweet\xnu\patches")
DST = Path(r"E:\ios-on-fuxi\xnu\patches")
DST.mkdir(parents=True, exist_ok=True)

# 只取"内核能起来"所需的早期补丁（工具链、机器配置、控制台、平台专家、定时器、启动 CPU）
WANT = list(range(1, 19))   # 0001..0018

def num(p: Path):
    m = re.match(r"(\d{4})", p.name)
    return int(m.group(1)) if m else 9999

copied = []
for f in sorted(SRC.iterdir()):
    if not f.is_file():
        continue
    n = num(f)
    if n not in WANT:
        continue
    text = f.read_text(encoding="utf-8", errors="replace")
    # 板级标识改名：SWEET -> FUXI，sweet -> fuxi
    text = text.replace("SWEET", "FUXI").replace("sweet", "fuxi")
    out = DST / f.name.replace("sweet", "fuxi")
    out.write_text(text, encoding="utf-8", newline="\n")
    copied.append(out.name)

print(f"已复制并改名 {len(copied)} 个补丁：")
for c in copied:
    print("  ", c)

# 确认没有残留 SWEET/sweet
left = 0
for f in DST.iterdir():
    if f.is_file() and f.suffix == ".patch":
        t = f.read_text(encoding="utf-8", errors="replace")
        if "SWEET" in t or "sweet" in t:
            print("!! 残留:", f.name)
            left += 1
print("残留文件数:", left)
