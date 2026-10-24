"""生成 0033：打印预链接段 / vm_kernel_slide / kalloc 类型元数据地址。"""

import io
import os
import shutil
import subprocess
import tempfile

FILES = [
    (r"E:\download\xnu-src\osfmk\arm64\arm_vm_init.c", "osfmk/arm64/arm_vm_init.c"),
    (r"E:\download\xnu-src\osfmk\kern\kalloc.c", "osfmk/kern/kalloc.c"),
]
OUT = r"E:\ios-on-fuxi\xnu\patches\0033-fuxi-slide-dump.patch"

work = tempfile.mkdtemp(prefix="slidedump-")
for src, rel in FILES:
    dst = os.path.join(work, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)


def run(cmd, check=True):
    r = subprocess.run(cmd, cwd=work, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        print("失败:", " ".join(cmd))
        print(r.stdout[-400:], r.stderr[-400:])
        raise SystemExit(1)
    return r


run(["git", "init", "-q", "."])
run(["git", "add", "-A"])
run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base"])

# ---------- arm_vm_init.c ----------
p = os.path.join(work, "osfmk", "arm64", "arm_vm_init.c")
t = io.open(p, encoding="utf-8").read()
a = """	vm_prelink_sdata = segPRELINKDATAB;
	vm_prelink_edata = segPRELINKDATAB + segSizePRELINKDATA;
"""
assert a in t
r = a + """
#if defined(ARM64_BOARD_CONFIG_FUXI)
	kprintf("FUXI VM: prelink_text=0x%lx/0x%lx plk_dc=0x%lx/0x%lx plk_te=0x%lx/0x%lx\\n",
	    (unsigned long)segPRELINKTEXTB, (unsigned long)segSizePRELINKTEXT,
	    (unsigned long)segPLKDATACONSTB, (unsigned long)segSizePLKDATACONST,
	    (unsigned long)segPLKTEXTEXECB, (unsigned long)segSizePLKTEXTEXEC);
	kprintf("FUXI VM: info=0x%lx/0x%lx plk_data=0x%lx/0x%lx prelink_etext=0x%lx\\n",
	    (unsigned long)segPRELINKINFOB, (unsigned long)segSizePRELINKINFO,
	    (unsigned long)segPRELINKDATAB, (unsigned long)segSizePRELINKDATA,
	    (unsigned long)vm_prelink_etext);
	kprintf("FUXI VM: slide=0x%lx gVirtBase=0x%lx textB=0x%lx linkedit=0x%lx\\n",
	    (unsigned long)vm_kernel_slide, (unsigned long)gVirtBase,
	    (unsigned long)segTEXTB, (unsigned long)segLINKB);
#endif
"""
t = t.replace(a, r, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(t)

# ---------- kalloc.c ----------
q = os.path.join(work, "osfmk", "kern", "kalloc.c")
k = io.open(q, encoding="utf-8").read()
lines = k.split("\n")
# 在 L986 前后插入打印
idx = None
for i, line in enumerate(lines):
    if "kt_sect->addr + vm_kernel_slide" in line:
        idx = i
        break
assert idx is not None, "没找到 kt_sect->addr + vm_kernel_slide"
indent = " " * (len(lines[idx]) - len(lines[idx].lstrip()))
lines.insert(idx, indent + "#if defined(ARM64_BOARD_CONFIG_FUXI)")
lines.insert(idx + 1, indent + 'kprintf("FUXI KALLOC: kt_sect->addr=0x%lx size=0x%lx slide=0x%lx -> 0x%lx\\n",')
lines.insert(idx + 2, indent + '    (unsigned long)kt_sect->addr, (unsigned long)kt_sect->size,')
lines.insert(idx + 3, indent + '    (unsigned long)vm_kernel_slide, (unsigned long)(kt_sect->addr + vm_kernel_slide));')
lines.insert(idx + 4, indent + "#endif")
io.open(q, "w", encoding="utf-8", newline="\n").write("\n".join(lines))

run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "dump"])
r = run(["git", "diff", "HEAD~1", "HEAD"])
io.open(OUT, "w", encoding="utf-8", newline="\n").write(r.stdout)
print(f"生成 {OUT.split(chr(92))[-1]}：{len(r.stdout)} 字节")
for line in r.stdout.split("\n"):
    if line.startswith(("+++", "@@", "+	kprintf", "+	kprintf")):
        print("  " + line[:110])

shutil.rmtree(work, ignore_errors=True)
