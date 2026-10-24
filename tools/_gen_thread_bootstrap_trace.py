"""生成 0035：在 arm_init 的 thread_bootstrap 前后打点，定位 getCpuDatap() 为 NULL 的根因。"""

import io
import os
import shutil
import subprocess
import tempfile

SRC = r"E:\download\xnu-src\osfmk\arm\arm_init.c"
OUT = r"E:\ios-on-fuxi\xnu\patches\0035-fuxi-thread-bootstrap-trace.patch"

work = tempfile.mkdtemp(prefix="btrace-")
os.makedirs(os.path.join(work, "osfmk", "arm"), exist_ok=True)
target = os.path.join(work, "osfmk", "arm", "arm_init.c")
shutil.copy2(SRC, target)


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

t = io.open(target, encoding="utf-8").read()

anchor = """	thread = thread_bootstrap();
	thread->machine.CpuDatap = &BootCpuData;
	thread->machine.pcpu_data_base = (vm_offset_t)0;
	machine_set_current_thread(thread);
"""
assert anchor in t, "锚点没找到"

new = """#if defined(ARM64_BOARD_CONFIG_FUXI)
	fuxi_early_mark(21, "calling thread_bootstrap");
#endif
	thread = thread_bootstrap();
#if defined(ARM64_BOARD_CONFIG_FUXI)
	fuxi_early_mark(22, "thread_bootstrap returned");
	kprintf("FUXI INIT: thread=%p BootCpuData=%p CpuDataEntries=%p\\n",
	    (void *)thread, (void *)&BootCpuData, (void *)CpuDataEntries);
#endif
	thread->machine.CpuDatap = &BootCpuData;
	thread->machine.pcpu_data_base = (vm_offset_t)0;
#if defined(ARM64_BOARD_CONFIG_FUXI)
	fuxi_early_mark(23, "calling machine_set_current_thread");
#endif
	machine_set_current_thread(thread);
#if defined(ARM64_BOARD_CONFIG_FUXI)
	{
		uint64_t tpidr;
		__asm__ volatile("mrs %0, tpidr_el1" : "=r"(tpidr));
		fuxi_early_mark(24, "machine_set_current_thread done");
		kprintf("FUXI INIT: TPIDR_EL1=0x%llx thread->CpuDatap=%p\\n",
		    (unsigned long long)tpidr, (void *)thread->machine.CpuDatap);
	}
#endif
"""
t = t.replace(anchor, new, 1)

# 需要 include
if "fuxi_early.h" not in t:
    t = t.replace('#include <arm/cpu_internal.h>',
                  '#include <arm/cpu_internal.h>\n#if defined(ARM64_BOARD_CONFIG_FUXI)\n#include <arm64/fuxi_early.h>\n#endif', 1)
io.open(target, "w", encoding="utf-8", newline="\n").write(t)

run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "trace"])
r = run(["git", "diff", "HEAD~1", "HEAD"])
io.open(OUT, "w", encoding="utf-8", newline="\n").write(r.stdout)
print(f"生成 {OUT.split(chr(92))[-1]}：{len(r.stdout)} 字节")
for line in r.stdout.split("\n"):
    if line.startswith(("+++", "@@", "+	fuxi_early", "+	kprintf", "+	uint64_t", "+	}")):
        print("  " + line[:110])

shutil.rmtree(work, ignore_errors=True)
