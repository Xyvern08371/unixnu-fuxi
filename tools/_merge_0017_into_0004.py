"""把 0017 的 pe_fiq.c 改动合并进 0004，解决"补丁互相冲突导致整体跳过"。

现状：
  · 0004 改了 pe_fiq.c（GICR 直接索引 / SGI 偏移 / GIC 组设置）
  · 0017 也改 pe_fiq.c（从 DT 读虚拟定时器 INTID）
  · 0004 先应用 -> 0017 的 pe_fiq hunk 冲突 -> 整个 0017 被跳过
  · 结果 0017 对 sleh.c（中断处理）的改动也没生效

做法：
  1. 以"原始 pe_fiq.c + 当前 0004 改动"为基线
  2. 再把 0017 的三处 pe_fiq 改动文本化地加进去
  3. 生成合并后的 hunk 替换 0004 里的 pe_fiq 段
  4. 从 0017 里删掉 pe_fiq 段（只留 sleh.c / protos.h）
"""

import io
import os
import shutil
import subprocess
import tempfile

SRC = r"E:\download\xnu-src\pexpert\arm\pe_fiq.c"
P0004 = r"E:\ios-on-fuxi\xnu\patches\0004-fuxi-machine-config.patch"
P0017 = r"E:\ios-on-fuxi\xnu\patches\0017-fuxi-device-tree-virtual-timer-irq.patch"

work = tempfile.mkdtemp(prefix="merge-pefiq-")
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

# --- 1) 应用当前 0004 的 pe_fiq 段 ---
t4 = io.open(P0004, encoding="utf-8").read()
i = t4.find("diff --git a/pexpert/arm/pe_fiq.c")
assert i >= 0
j = t4.find("diff --git ", i + 10)
sec4 = t4[i:j if j > 0 else len(t4)]
part = os.path.join(work, "p4.patch")
io.open(part, "w", encoding="utf-8", newline="\n").write(sec4)
run(["git", "apply", "-p1", part])
print("0004 的 pe_fiq 已应用")

# --- 2) 文本化加入 0017 的三处改动 ---
p = os.path.join(work, "pexpert", "arm", "pe_fiq.c")
src = io.open(p, encoding="utf-8").read()

# 2a) include
old = "#include <stdint.h>\n#include <arm64/proc_reg.h>"
new = "#include <stdint.h>\n#include <libkern/section_keywords.h>\n#include <arm64/proc_reg.h>"
assert old in src, "include 锚点没找到"
src = src.replace(old, new, 1)

# 2b) fuxi_vtimer_intid 定义
old = 'MACHINE_TIMEOUT(gicr_wake_timeout_ns, "gicr-wake-timeout", GICR_WAKE_TIMEOUT_NS, MACHINE_TIMEOUT_UNIT_NSEC, NULL);'
new = old + '''

#if defined(ARM64_BOARD_CONFIG_FUXI)
/* Phone default; QEMU virt wires the architected virtual timer to INTID 27. */
SECURITY_READ_ONLY_LATE(uint32_t) fuxi_vtimer_intid = FUXI_VTIMER_INTID;
#endif'''
assert old in src, "MACHINE_TIMEOUT 锚点没找到"
src = src.replace(old, new, 1)

# 2c) 从 DT 读 INTID
old = '''		if (prop_size < 4 * sizeof(uint64_t)) {
			panic("%s: incorrect reg property size in GIC DT node; expecting 32 bytes but got %u bytes", __func__, prop_size);
		}
'''
new = old + '''
#if defined(ARM64_BOARD_CONFIG_FUXI)
		/* Read only on the boot CPU, before the GIC and RO-late lockdown. */
		void const *timer_prop;
		unsigned int timer_size;
		if (SecureDTGetProperty(entry, "virtual-timer-intid", &timer_prop, &timer_size) == kSuccess) {
			if (timer_size != sizeof(uint32_t)) {
				panic("%s: invalid virtual-timer-intid size %u", __func__, timer_size);
			}
			uint32_t intid = *(const uint32_t *)timer_prop;
			if (intid < 16 || intid >= 32) {
				panic("%s: virtual timer INTID %u is not a PPI", __func__, intid);
			}
			fuxi_vtimer_intid = intid;
		}
		kprintf("FUXI GIC: virtual timer INTID %u\\n", fuxi_vtimer_intid);
#endif
'''
assert old in src, "prop_size 锚点没找到"
src = src.replace(old, new, 1)

# 2d) GICR 使能改成用 fuxi_vtimer_intid
old = "gicr_write32(0x10000 + GICR_ISENABLER0, (1U << FUXI_VTIMER_INTID) | (1U << FUXI_IPI_SGI));"
new = "gicr_write32(0x10000 + GICR_ISENABLER0, (1U << fuxi_vtimer_intid) | (1U << FUXI_IPI_SGI));"
if old in src:
    src = src.replace(old, new, 1)
    print("GICR ISENABLER 改用 fuxi_vtimer_intid")

io.open(p, "w", encoding="utf-8", newline="\n").write(src)
run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "merged"])

# --- 3) 生成合并后的 hunk，替换 0004 ---
r = run(["git", "diff", "HEAD~1", "HEAD", "--", "pexpert/arm/pe_fiq.c"])
new_sec = r.stdout
assert new_sec.strip()
t4_new = t4[:i] + new_sec + (t4[j:] if j > 0 else "")
io.open(P0004, "w", encoding="utf-8", newline="\n").write(t4_new)
print(f"0004 的 pe_fiq 段已更新（{len(sec4)} -> {len(new_sec)} 字节）")

# --- 4) 从 0017 里删掉 pe_fiq 段 ---
t17 = io.open(P0017, encoding="utf-8").read()
a = t17.find("diff --git a/pexpert/arm/pe_fiq.c")
if a >= 0:
    b = t17.find("diff --git ", a + 10)
    t17 = t17[:a] + (t17[b:] if b > 0 else "")
    io.open(P0017, "w", encoding="utf-8", newline="\n").write(t17)
    print("0017 已移除 pe_fiq 段（保留 sleh.c / protos.h）")

shutil.rmtree(work, ignore_errors=True)
