"""用真实的 pe_fiq.c 生成合并后的 patch 片段（GICR 直接索引 + 原有的 group/priority 改动）。

做法：
1) 拿原始 pe_fiq.c
2) 先应用现有 0004 里那段 pe_fiq hunk
3) 再插入 FUXI 的 GICR 直接索引代码
4) git diff 生成正确的 hunk，替换回 0004
"""

import io
import os
import re
import shutil
import subprocess
import tempfile

SRC = r"E:\download\xnu-src\pexpert\arm\pe_fiq.c"
PATCH = r"E:\ios-on-fuxi\xnu\patches\0004-fuxi-machine-config.patch"

work = tempfile.mkdtemp(prefix="pefiq-")
target = os.path.join(work, "pexpert", "arm")
os.makedirs(target, exist_ok=True)
shutil.copy2(SRC, os.path.join(target, "pe_fiq.c"))

def run(cmd, cwd=work, check=True):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        print("命令失败:", " ".join(cmd))
        print(r.stdout[-1500:])
        print(r.stderr[-1500:])
        raise SystemExit(1)
    return r

run(["git", "init", "-q", "."])
run(["git", "add", "-A"])
run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base"])

# 1) 提取现有 0004 里的 pe_fiq 片段并应用
text = io.open(PATCH, encoding="utf-8").read()
i = text.find("diff --git a/pexpert/arm/pe_fiq.c")
if i < 0:
    i = text.find("diff --git a/pexpert/pexpert/arm/pe_fiq.c")
assert i >= 0, "0004 里没有 pe_fiq 片段"
j = text.find("diff --git ", i + 10)
old_section = text[i:j if j > 0 else len(text)]

part = os.path.join(work, "old.patch")
io.open(part, "w", encoding="utf-8", newline="\n").write(old_section)
run(["git", "apply", "-p1", part])
run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "old-hunk"])
print("已应用原有 pe_fiq 改动")

# 2) 插入 FUXI 的 GICR 直接索引
p = os.path.join(target, "pe_fiq.c")
src = io.open(p, encoding="utf-8").read()

anchor = """	uint32_t phys_id = __builtin_arm_rsr64("MPIDR_EL1") & (MPIDR_AFF1_MASK | MPIDR_AFF0_MASK);

	for (vm_offset_t offset = 0; offset < gicr_size; offset += GICR_PE_SIZE) {"""
assert anchor in src, "find_gicr_pe_base 的循环锚点没找到"

insert = """	uint32_t phys_id = __builtin_arm_rsr64("MPIDR_EL1") & (MPIDR_AFF1_MASK | MPIDR_AFF0_MASK);

#if defined(ARM64_BOARD_CONFIG_FUXI)
	/*
	 * fuxi(SM8550) 的 redistributor 是固定布局：基址 0x17180000，每个 0x40000，
	 * 共 8 个（0x200000）。原来的线性扫描（按 TYPER affinity 匹配、步长
	 * GICR_PE_SIZE）在这台机器上会走到区间外，触发同步外部中止（panic 在
	 * pe_init_fiq）。这里直接按 MPIDR 的 Aff0 索引。
	 */
	{
		uint32_t idx = phys_id & 0xFF;

		if (((uint64_t)(idx + 1) * GICR_PE_SIZE) <= gicr_size) {
			return gicr_base + (vm_offset_t)idx * GICR_PE_SIZE;
		}
		panic("%s: core %u out of GICR range (idx=%u size=%lu)",
		    __func__, ml_get_cpu_number(phys_id), idx, (unsigned long)gicr_size);
	}
#endif

	for (vm_offset_t offset = 0; offset < gicr_size; offset += GICR_PE_SIZE) {"""
src = src.replace(anchor, insert, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(src)
run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "gicr-direct"])

# 3) 生成合并 diff
r = run(["git", "diff", "HEAD~2", "HEAD", "--", "pexpert/arm/pe_fiq.c"])
new_section = r.stdout
assert new_section.strip(), "git diff 为空"

# 4) 替换回 0004
new_text = text[:i] + new_section + (text[j:] if j > 0 else "")
io.open(PATCH, "w", encoding="utf-8", newline="\n").write(new_text)

print(f"已用新片段替换（{len(old_section)} -> {len(new_section)} 字节）")
print()
print(new_section[:1200])
shutil.rmtree(work, ignore_errors=True)
