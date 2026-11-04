"""修正 FUXI 的 GICR 寄存器偏移：SGI 帧在 +0x10000。

XNU 头里 GICR_IGROUPR0/GICR_IPRIORITYR0/GICR_ISENABLER0 是相对 SGI 帧的偏移
（0x080/0x400/0x100），而 gicr_pe_base 指向的是 RD 帧基址，所以写的时候要
自己加上 0x10000。真机上不加就写进 RD 帧的保留区 -> 同步外部中止
（panic far = gicr_base + 0x80）。

用真实源码重新生成 pe_fiq hunk（保留已有的 GICR 直接索引等改动）。
"""

import io
import os
import shutil
import subprocess
import tempfile

SRC = r"E:\download\xnu-src\pexpert\arm\pe_fiq.c"
PATCH = r"E:\ios-on-fuxi\xnu\patches\0004-fuxi-machine-config.patch"

work = tempfile.mkdtemp(prefix="pefiq2-")
os.makedirs(os.path.join(work, "pexpert", "arm"), exist_ok=True)
shutil.copy2(SRC, os.path.join(work, "pexpert", "arm", "pe_fiq.c"))


def run(cmd, check=True):
    r = subprocess.run(cmd, cwd=work, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        print("失败:", " ".join(cmd))
        print(r.stdout[-800:], r.stderr[-800:])
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
print("已应用当前 pe_fiq 改动")

p = os.path.join(work, "pexpert", "arm", "pe_fiq.c")
src = io.open(p, encoding="utf-8").read()

# 在 FUXI 块里加 SGI 偏移定义，并给三个写操作加上它
old_block = """	gicr_write32(GICR_IGROUPR0, 0xFFFFFFFF);
	for (unsigned int i = 0; i < 32; i += 4) {
		gicr_write32(GICR_IPRIORITYR0 + i, 0xA0A0A0A0);
	}
	gicr_write32(GICR_ISENABLER0, (1U << FUXI_VTIMER_INTID) | (1U << FUXI_IPI_SGI));"""

new_block = """	/*
	 * GICv3 的 redistributor 分两帧：RD 帧（0x00000，TYPER/WAKER 等）和
	 * SGI 帧（0x10000，IGROUPR/IPRIORITYR/ISENABLER）。gicr_pe_base 指向
	 * RD 帧，所以写 SGI 帧的寄存器要自己加 0x10000，否则写到保留区，
	 * 真机上直接同步外部中止。
	 */
	gicr_write32(0x10000 + GICR_IGROUPR0, 0xFFFFFFFF);
	for (unsigned int i = 0; i < 32; i += 4) {
		gicr_write32(0x10000 + GICR_IPRIORITYR0 + i, 0xA0A0A0A0);
	}
	gicr_write32(0x10000 + GICR_ISENABLER0, (1U << FUXI_VTIMER_INTID) | (1U << FUXI_IPI_SGI));"""

assert old_block in src, "FUXI 的 GICR 写块没找到"
src = src.replace(old_block, new_block, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(src)
run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "sgi-offset"])

r = run(["git", "diff", "HEAD~2", "HEAD", "--", "pexpert/arm/pe_fiq.c"])
new_section = r.stdout
assert new_section.strip()

new_text = text[:i] + new_section + (text[j:] if j > 0 else "")
io.open(PATCH, "w", encoding="utf-8", newline="\n").write(new_text)
print(f"已重新生成 pe_fiq 片段（{len(section)} -> {len(new_section)} 字节）")
print()
print(new_section[:900])
shutil.rmtree(work, ignore_errors=True)
