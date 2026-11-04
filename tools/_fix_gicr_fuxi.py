"""fuxi: 用直接索引替代 find_gicr_pe_base() 的扫描逻辑。

原实现：
    for (offset = 0; offset < gicr_size; offset += GICR_PE_SIZE) {
        gicr_pe_base = gicr_base + offset;
        typer = gicr_read64(GICR_TYPER);
        if (affinity == phys_id) return gicr_pe_base;
        if (typer & LAST) break;
    }
在 fuxi 上会踩到 GICR 区间外（外部中止）。

fuxi 的布局是固定的：8 个 redistributor，基址 0x17180000，每个 0x40000，
共 0x200000。直接按 MPIDR 的 Aff0 索引即可，不需要扫描。

同时修掉 proc_reg.h 里漏掉的 `defined (FUXI)`（带空格那种）。
"""

import io

P = r"E:\ios-on-fuxi\xnu\patches\0004-fuxi-machine-config.patch"
t = io.open(P, encoding="utf-8").read()

# ---- 1) proc_reg.h 里漏掉的 defined (FUXI) ----
n = t.count("defined (FUXI)")
if n:
    t = t.replace("defined (FUXI)", "defined (ARM64_BOARD_CONFIG_FUXI)")
    print(f"proc_reg.h: 修正 {n} 处 defined (FUXI)")

# ---- 2) find_gicr_pe_base 的 FUXI 分支 ----
if "FUXI_GICR_DIRECT_INDEX" not in t:
    old = """ static vm_offset_t
 find_gicr_pe_base()
 {
 	// We only care about aff1 and aff0
 	uint32_t phys_id = __builtin_arm_rsr64("MPIDR_EL1") & (MPIDR_AFF1_MASK | MPIDR_AFF0_MASK);

 	for (vm_offset_t offset = 0; offset < gicr_size; offset += GICR_PE_SIZE) {"""

    new = """ static vm_offset_t
 find_gicr_pe_base()
 {
 	// We only care about aff1 and aff0
 	uint32_t phys_id = __builtin_arm_rsr64("MPIDR_EL1") & (MPIDR_AFF1_MASK | MPIDR_AFF0_MASK);

+#if defined(ARM64_BOARD_CONFIG_FUXI)
+	/*
+	 * FUXI_GICR_DIRECT_INDEX
+	 *
+	 * fuxi(SM8550) 的 redistributor 是固定布局：基址 0x17180000，
+	 * 每个 0x40000，共 8 个（0x200000）。原来的线性扫描（按 TYPER 的
+	 * affinity 匹配、步长 GICR_PE_SIZE）会走到区间外，触发同步外部中止。
+	 * 这里直接按 MPIDR 的 Aff0 索引。
+	 */
+	{
+		uint32_t idx = phys_id & 0xFF;
+
+		if (((uint64_t)(idx + 1) * GICR_PE_SIZE) <= gicr_size) {
+			return gicr_base + (vm_offset_t)idx * GICR_PE_SIZE;
+		}
+		panic("%s: core %u out of GICR range (idx=%u size=%lu)",
+		    __func__, ml_get_cpu_number(phys_id), idx, (unsigned long)gicr_size);
+	}
+#endif
+
 	for (vm_offset_t offset = 0; offset < gicr_size; offset += GICR_PE_SIZE) {"""

    assert old in t, "find_gicr_pe_base hunk 锚点没找到"
    t = t.replace(old, new, 1)
    io.open(P, "w", encoding="utf-8", newline="\n").write(t)
    print("已加 FUXI 直接索引分支")
else:
    io.open(P, "w", encoding="utf-8", newline="\n").write(t)
    print("已有 FUXI 直接索引分支")

# 检查 hunk 行数是否需要修正（这里只是加行，行数在 @@ 里；git apply 依赖 @@ 计数）
import re
print("\n=== 检查该 hunk 的 @@ 计数 ===")
for m in re.finditer(r"@@ -(\d+),(\d+) \+(\d+),(\d+) @@", t):
    pass
print("（如果 apply 失败我再修计数）")
