"""把 GICR 诊断值打印挪到"平台专家注册完成"之后（那时控制台已就绪，输出不会被清屏冲掉）。

做法：
  1) pe_fiq.c：把早期帧缓冲打印改成写入 6 个全局变量
  2) SweetPlatformExpert.cpp（patch 0016）：注册完成后 kprintf 这 6 个值
"""

import io
import os
import shutil
import subprocess
import tempfile

SRC = r"E:\download\xnu-src\pexpert\arm\pe_fiq.c"
P0004 = r"E:\ios-on-fuxi\xnu\patches\0004-fuxi-machine-config.patch"
P0016 = r"E:\ios-on-fuxi\xnu\patches\0016-fuxi-device-tree-platform-expert.patch"

work = tempfile.mkdtemp(prefix="gicr-late-")
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

t4 = io.open(P0004, encoding="utf-8").read()
i = t4.find("diff --git a/pexpert/arm/pe_fiq.c")
assert i >= 0
j = t4.find("diff --git ", i + 10)
sec4 = t4[i:j if j > 0 else len(t4)]

part = os.path.join(work, "p4.patch")
io.open(part, "w", encoding="utf-8", newline="\n").write(sec4)
run(["git", "apply", "-p1", part])
run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "cur"])

p = os.path.join(work, "pexpert", "arm", "pe_fiq.c")
src = io.open(p, encoding="utf-8").read()

# 1) 删掉早期打印的 helper 和调用，改成写全局
start = src.find("#if defined(ARM64_BOARD_CONFIG_FUXI)\nextern void fuxi_early_putc(char c);")
if start >= 0:
    end = src.find("#endif\n\n", start)
    src = src[:start] + src[end + len("#endif\n\n"):]

old_call_start = src.find("#if defined(ARM64_BOARD_CONFIG_FUXI)\n\tfuxi_early_puts(\"GICD \");")
assert old_call_start >= 0, "早期打印调用块没找到"
old_call_end = src.find("#endif", old_call_start) + len("#endif")

new_call = """#if defined(ARM64_BOARD_CONFIG_FUXI)
	fuxi_gic_dbg[0] = (uint64_t)gicd_base;
	fuxi_gic_dbg[1] = (uint64_t)gicr_base;
	fuxi_gic_dbg[2] = (uint64_t)gicr_size;
	fuxi_gic_dbg[3] = (uint64_t)gicr_pe_base;
	fuxi_gic_dbg[4] = (uint64_t)GICR_IGROUPR0;
	fuxi_gic_dbg[5] = (uint64_t)GICR_WAKER;
#endif"""
src = src[:old_call_start] + new_call + src[old_call_end:]

# 2) 加全局变量定义（放在 gicr_size 定义之后）
anchor = "static vm_offset_t gicr_size;"
assert anchor in src
src = src.replace(anchor, anchor + "\n\n/* GICR 诊断值，供平台专家在控制台就绪后打印 */\nuint64_t fuxi_gic_dbg[6];", 1)

io.open(p, "w", encoding="utf-8", newline="\n").write(src)
run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "globals"])

r = run(["git", "diff", "HEAD~2", "HEAD", "--", "pexpert/arm/pe_fiq.c"])
new_sec = r.stdout
assert new_sec.strip()
io.open(P0004, "w", encoding="utf-8", newline="\n").write(
    t4[:i] + new_sec + (t4[j:] if j > 0 else ""))
print("pe_fiq.c: 改为写全局 fuxi_gic_dbg[6]")

# 3) 平台专家里打印
t16 = io.open(P0016, encoding="utf-8").read()
anchor16 = '+\tIOLog("FUXI: platform expert registered\\n");'
assert anchor16 in t16, "平台专家注册日志没找到"
add16 = anchor16 + """
+
+#if defined(ARM64_BOARD_CONFIG_FUXI)
+\t{
+\t\textern uint64_t fuxi_gic_dbg[6];
+\t\tIOLog("FUXI GICR: gicd=%llx gicr=%llx size=%llx pe=%llx IGROUPR0=%llx WAKER=%llx\\n",
+\t\t    fuxi_gic_dbg[0], fuxi_gic_dbg[1], fuxi_gic_dbg[2],
+\t\t    fuxi_gic_dbg[3], fuxi_gic_dbg[4], fuxi_gic_dbg[5]);
+\t}
+#endif"""
t16 = t16.replace(anchor16, add16, 1)
io.open(P0016, "w", encoding="utf-8", newline="\n").write(t16)
print("0016: 平台专家注册后打印 GICR 六个值")

shutil.rmtree(work, ignore_errors=True)
