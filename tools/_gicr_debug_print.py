"""在 pe_init_fiq 里打印 GICR 相关实参，一次构建拿到真相。

要打印：
  gicr_base / gicr_size / gicd_base / soc_base_phys
  find_gicr_pe_base 的返回值
  GICR_IGROUPR0 / GICR_WAKER 两个常量的实际数值

这样就能确定到底该不该加 0x10000，以及映射是否有效。
"""

import io
import os
import shutil
import subprocess
import tempfile

SRC = r"E:\download\xnu-src\pexpert\arm\pe_fiq.c"
PATCH = r"E:\ios-on-fuxi\xnu\patches\0004-fuxi-machine-config.patch"

work = tempfile.mkdtemp(prefix="gicr-dbg-")
os.makedirs(os.path.join(work, "pexpert", "arm"), exist_ok=True)
shutil.copy2(SRC, os.path.join(work, "pexpert", "arm", "pe_fiq.c"))


def run(cmd, check=True):
    r = subprocess.run(cmd, cwd=work, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        print("失败:", " ".join(cmd))
        print(r.stdout[-600:], r.stderr[-600:])
        raise SystemExit(1)
    return r


run(["git", "init", "-q", "."])
run(["git", "add", "-A"])
run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base"])

text = io.open(PATCH, encoding="utf-8").read()
i = text.find("diff --git a/pexpert/arm/pe_fiq.c")
assert i >= 0
j = text.find("diff --git ", i + 10)
section = text[i:j if j > 0 else len(text)]

part = os.path.join(work, "cur.patch")
io.open(part, "w", encoding="utf-8", newline="\n").write(section)
run(["git", "apply", "-p1", part])
run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "cur"])
print("当前 pe_fiq 改动已应用")

p = os.path.join(work, "pexpert", "arm", "pe_fiq.c")
src = io.open(p, encoding="utf-8").read()

# 在 find_gicr_pe_base 调用之后打印所有实参
old = "\t// Find the redistributor for this processor\n\tvm_offset_t gicr_pe_base = find_gicr_pe_base();"
assert old in src, "find_gicr_pe_base 调用点没找到"

new = """\t// Find the redistributor for this processor
\tvm_offset_t gicr_pe_base = find_gicr_pe_base();

#if defined(ARM64_BOARD_CONFIG_FUXI)
\tkprintf("FUXI GICR: gicd=%p gicr=%p size=%p pe=%p IGROUPR0=0x%x WAKER=0x%x\\n",
\t    (void *)gicd_base, (void *)gicr_base, (void *)gicr_size, (void *)gicr_pe_base,
\t    (unsigned)GICR_IGROUPR0, (unsigned)GICR_WAKER);
#endif"""

src = src.replace(old, new, 1)

# 把 SGI 偏移去掉（先按头文件原值试）
src = src.replace("gicr_write32(0x10000 + GICR_IGROUPR0, 0xFFFFFFFF);",
                  "gicr_write32(GICR_IGROUPR0, 0xFFFFFFFF);")
src = src.replace("gicr_write32(0x10000 + GICR_IPRIORITYR0 + i, 0xA0A0A0A0);",
                  "gicr_write32(GICR_IPRIORITYR0 + i, 0xA0A0A0A0);")
src = src.replace("gicr_write32(0x10000 + GICR_ISENABLER0, (1U << fuxi_vtimer_intid) | (1U << FUXI_IPI_SGI));",
                  "gicr_write32(GICR_ISENABLER0, (1U << fuxi_vtimer_intid) | (1U << FUXI_IPI_SGI));")

io.open(p, "w", encoding="utf-8", newline="\n").write(src)
run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "debug"])

r = run(["git", "diff", "HEAD~2", "HEAD", "--", "pexpert/arm/pe_fiq.c"])
new_sec = r.stdout
assert new_sec.strip()

io.open(PATCH, "w", encoding="utf-8", newline="\n").write(
    text[:i] + new_sec + (text[j:] if j > 0 else ""))

print("已加入 GICR 实参打印，并去掉重复的 SGI 偏移")
print()
for line in new_sec.split("\n"):
    if "GICR" in line or "kprintf" in line:
        print("  " + line)

shutil.rmtree(work, ignore_errors=True)
