"""生成 0038：导出 init_thread，让 arm_init 早期可以直接用它设 TPIDR_EL1。

0037 里调用了 thread_bootstrap() 来拿 thread，但它内部会调 timer_init()，
在 arm_init 那个位置 timer 子系统还没起来，会引入新的崩溃。

这里改成：
  - 在 thread.c 里加一个 fuxi_init_thread() 返回 &init_thread（不碰 timer）
  - arm_init 早期只设置 TPIDR_EL1 和 machine 的关键字段
"""

import io
import os
import shutil
import subprocess
import tempfile

FILES = [
    (r"E:\download\xnu-src\osfmk\arm\arm_init.c", "osfmk/arm/arm_init.c"),
    (r"E:\download\xnu-src\osfmk\kern\thread.c", "osfmk/kern/thread.c"),
]
OUT = r"E:\ios-on-fuxi\xnu\patches\0038-fuxi-init-thread-export.patch"

work = tempfile.mkdtemp(prefix="ith-")
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

# ---- thread.c: 导出 init_thread ----
p = os.path.join(work, "osfmk", "kern", "thread.c")
t = io.open(p, encoding="utf-8").read()
a = """__startup_func
thread_t
thread_bootstrap(void)
{
"""
assert a in t, "thread_bootstrap 锚点没找到"
t = t.replace(a, """#if defined(ARM64_BOARD_CONFIG_FUXI)
/*
 * arm_init 需要在 PE_init_platform() 之前就设好 TPIDR_EL1，
 * 但那时不能调 thread_bootstrap()（它会调 timer_init）。
 * 这里只把静态的 init_thread 交出去，让调用方自己填 machine 字段。
 */
thread_t
fuxi_init_thread(void)
{
	return &init_thread;
}
#endif

""" + a, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(t)

# ---- arm_init.c: 用 fuxi_init_thread ----
q = os.path.join(work, "osfmk", "arm", "arm_init.c")
s = io.open(q, encoding="utf-8").read()

anchor = """	cpu_data_init(&BootCpuData);
#if defined(HAS_APPLE_PAC)
"""
assert anchor in s, "cpu_data_init 锚点没找到"

insert = """	cpu_data_init(&BootCpuData);
#if defined(ARM64_BOARD_CONFIG_FUXI)
	/*
	 * start.s 进入 arm_init 前执行过 msr TPIDR_EL1, xzr，
	 * 紧接着的 PE_init_platform() 会加锁 -> get_preemption_level()
	 * -> current_thread() -> 读 [TPIDR + 0x230]，TPIDR 为 0 时崩。
	 * ml_get_timebase()（读 +0x228）同理。
	 *
	 * 这里只把 TPIDR_EL1 指向静态的 init_thread 并填好 machine 的
	 * 三个早期字段；不调用 thread_bootstrap()（它要 timer_init）。
	 * 下面原本的 thread_bootstrap() 之后会用真值覆盖。
	 */
	{
		extern thread_t fuxi_init_thread(void);
		thread_t early_thread = fuxi_init_thread();

		early_thread->machine.CpuDatap = &BootCpuData;
		early_thread->machine.pcpu_data_base = (vm_offset_t)0;
		early_thread->machine.preemption_count = 0;
		machine_set_current_thread(early_thread);
		kprintf("FUXI INIT: early thread=%p\\n", (void *)early_thread);
	}
#endif
#if defined(HAS_APPLE_PAC)
"""
s = s.replace(anchor, insert, 1)
io.open(q, "w", encoding="utf-8", newline="\n").write(s)

run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "export-init-thread"])
r = run(["git", "diff", "HEAD~1", "HEAD"])
io.open(OUT, "w", encoding="utf-8", newline="\n").write(r.stdout)
print(f"生成 {OUT.split(chr(92))[-1]}：{len(r.stdout)} 字节")
for line in r.stdout.split("\n"):
    if line.startswith(("+++", "@@", "+")):
        print("  " + line[:110])

shutil.rmtree(work, ignore_errors=True)
