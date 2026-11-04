"""把 ios-sweet 的 ADT 工具与 mkadt/mkpayload 移植成 fuxi 版。

做法：
  1. adt.py           -> tools/iosadt.py        （原样复制，只改模块名引用）
  2. mkadt.py         -> tools/mkadt_fuxi.py    （替换硬件常量与板级标识）
  3. mkpayload.py     -> tools/mkpayload_fuxi.py（替换 magic 与命名）

fuxi（SM8550）的硬件常量来源：真机导出的 rom/device/fuxi_runtime.dtb
  GICD 0x17100000 (0x10000) / GICR 0x17180000 (0x200000)
  UFS  0x01d84000 (0x3000)   —— 和 sweet 相同
  FB   0xB0000000 (0x9E4000) —— 来自 UEFI GOP
  定时器 19.2 MHz，虚拟定时器 INTID 19（高通编号与 sweet 一致）
"""

import io
import re
from pathlib import Path

SRC = Path(r"E:\download\ios-sweet\tools")
DST = Path(r"E:\ios-on-fuxi\tools")

# ---------- 1) adt.py -> iosadt.py ----------
s = (SRC / "adt.py").read_text(encoding="utf-8")
(DST / "iosadt.py").write_text(s, encoding="utf-8", newline="\n")
print("已生成 tools/iosadt.py")

# ---------- 2) mkadt.py -> mkadt_fuxi.py ----------
s = (SRC / "mkadt.py").read_text(encoding="utf-8")

repl = [
    # 模块名
    ("import adt  # noqa: E402", "import iosadt as adt  # noqa: E402"),
    # 板级标识
    ("SWEET", "FUXI"),
    ("sweet", "fuxi"),
    # 硬件常量：fuxi / SM8550
    ("PHYS_BASE = 0xb0000000\nMEM_SIZE = 0x4d000000",
     "PHYS_BASE = 0x100000000\nMEM_SIZE = 0xfcc00000"),
    ("HIGH_PHYS_BASE = 0x100000000\nHIGH_MEM_SIZE = 0xfcc00000",
     "HIGH_PHYS_BASE = 0x100000000\nHIGH_MEM_SIZE = 0xfcc00000"),
    ("GICD, GICD_SIZE = 0x17a00000, 0x10000", "GICD, GICD_SIZE = 0x17100000, 0x10000"),
    ("GICR, GICR_SIZE = 0x17a60000, 0x100000", "GICR, GICR_SIZE = 0x17180000, 0x200000"),
    ("FB, FB_SIZE = 0x9c000000, 0x1700000", "FB, FB_SIZE = 0xB0000000, 0x9E4000"),
    ("UFS, UFS_SIZE = 0x01d84000, 0x3000", "UFS, UFS_SIZE = 0x01d84000, 0x3000"),
    # 合成 ECID：'FUXI' + 1
    ("FUXI_ECID = 0x5357454554000001  # 'FUXI' + 1, synthetic",
     "FUXI_ECID = 0x4655584900000001  # 'FUXI' + 1, synthetic"),
    # 根节 identity
    ("cstr('xiaomi,fuxi') + cstr('qcom,sm7150')",
     "cstr('xiaomi,fuxi') + cstr('qcom,sm8550')"),
    # CPU 型号与频率（SM8550: 1x X3 + 4x A715 + 3x A510）
    ("cstr('qcom,kryo470')", "cstr('qcom,kryo715')"),
    ("('clock-frequency', u32(2304000000 if core >= 6 else 1804800000)),",
     "('clock-frequency', u32(3200000000 if core == 0 else (2800000000 if core <= 4 else 2000000000))),"),
    ("('compatible', cstr('fuxi-shim')),", "('compatible', cstr('fuxi-shim')),"),
    ("hashlib.sha384(b'fuxi boot manifest').digest()", "hashlib.sha384(b'fuxi boot manifest').digest()"),
]
for a, b in repl:
    s = s.replace(a, b)

# 输出路径说明（fuxi 的 ADT 产物名）
s = s.replace('"""Build the minimal Apple Device Tree that the FUXI xnu needs to boot.',
              '"""为 fuxi（SM8550）生成 XNU 启动所需的最小 Apple 设备树。')

(DST / "mkadt_fuxi.py").write_text(s, encoding="utf-8", newline="\n")
print("已生成 tools/mkadt_fuxi.py")

# ---------- 3) mkpayload.py -> mkpayload_fuxi.py ----------
p = (SRC / "mkpayload.py").read_text(encoding="utf-8")
p = p.replace('"SWEETXNU"', '"FUXIXNU"')
p = p.replace("'SWEETXNU'", "'FUXIXNU'")
p = p.replace("sweet", "fuxi").replace("SWEET", "FUXI")
p = p.replace("import adt", "import iosadt as adt")
(DST / "mkpayload_fuxi.py").write_text(p, encoding="utf-8", newline="\n")
print("已生成 tools/mkpayload_fuxi.py")

# ---------- 校验：常量是否替换到位 ----------
for name in ("mkadt_fuxi.py", "mkpayload_fuxi.py"):
    t = (DST / name).read_text(encoding="utf-8")
    print(f"\n=== {name} 关键常量 ===")
    for pat in (r"GICD, GICD_SIZE.*", r"GICR, GICR_SIZE.*", r"FB, FB_SIZE.*",
                r"PHYS_BASE = .*", r"FUXI_ECID.*", r"FUXIXNU"):
        for m in re.finditer(pat, t):
            print("  ", m.group(0)[:90])
            break
    if "sweet" in t.lower():
        print("  !! 仍有 sweet 残留")
