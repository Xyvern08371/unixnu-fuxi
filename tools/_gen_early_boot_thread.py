"""生成 0037：把 thread_bootstrap + machine_set_current_thread 提前到 arm_init 开头。

问题：
  XNU 的 start.s 在跳进 arm_init 之前主动清掉 TPIDR_EL1（start.s:765），
  而 arm_init 在 L363 就调用 PE_init_platform() —— 它内部加锁会走
  get_preemption_level() -> current_thread() -> TPIDR_EL1(=0) -> 解引用 NULL
  （FAR=0x230）。ml_get_timebase 同理（FAR=0x228）。

  Apple 设备上 iBoot 交棒时会另有一条路径先建立起 thread，我们没有。

修法：
  把 L442-445 的 thread 建立提到 cpu_data_init() 之后、PE_init_platform() 之前，
  让 TPIDR_EL1 从一开始就有效。原位置保留（幂等）。
"""

import io
import os
import shutil
import subprocess
import tempfile

SRC = r"E:\download\xnu-src\osfmk\arm\arm_init.c"
OUT = r"E:\ios-on-fuxi\xnu\patches\0037-fuxi-early-boot-thread.patch"

work = tempfile.mkdtemp(prefix="ebt-")
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

anchor = """	cpu_data_init(&BootCpuData);
#if defined(HAS_APPLE_PAC)
"""
assert anchor in t, "cpu_data_init 锚点没找到"

insert = """	cpu_data_init(&BootCpuData);
#if defined(ARM64_BOARD_CONFIG_FUXI)
	/*
	 * 把 boot thread 的建立提前到这里。
	 *
	 * start.s 进入 arm_init 前刚执行过 msr TPIDR_EL1, xzr（清空 thread 指针），
	 * 而紧随其后的 PE_init_platform() 会加锁 -> get_preemption_level()
	 * -> current_thread() -> 读 [TPIDR_EL1 + 0x230]，TPIDR 为 0 时直接崩。
	 * ml_get_timebase()（读 +0x228）同理。
	 *
	 * 原来这段在函数末尾（thread_bootstrap 之后），对早期路径来说太晚了。
	 * 内核自身不依赖重复调用，这里建立之后下面的原逻辑仍会覆盖一次，
	 * 保持行为一致。
	 */
	{
		/*
		 * 只设置 TPIDR_EL1，不调用 thread_bootstrap()。
		 * thread_bootstrap() 里会调 timer_init()，而 arm_init 这个位置
		 * timer 子系统还没起来，会引入新的崩溃。
		 * init_thread 是 thread.c 里的静态结构，已经随 BSS 清零，
		 * 这里直接把 TPIDR 指向它并补上 machine 的关键字段，
		 * 等下面原本的 thread_bootstrap() 跑完会用真值覆盖。
		 */
		extern thread_t fuxi_init_thread(void);
		thread_t early_thread = fuxi_init_thread();

		early_thread->machine.CpuDatap = &BootCpuData;
		early_thread->machine.pcpu_data_base = (vm_offset_t)0;
		early_thread->machine.preemption_count = 0;
		machine_set_current_thread(early_thread);
		kprintf("FUXI INIT: early thread=%p (no thread_bootstrap)\\n",
		    (void *)early_thread);
	}
#endif
#if defined(HAS_APPLE_PAC)
"""
t = t.replace(anchor, insert, 1)
io.open(target, "w", encoding="utf-8", newline="\n").write(t)

run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "early-thread"])
r = run(["git", "diff", "HEAD~1", "HEAD"])
io.open(OUT, "w", encoding="utf-8", newline="\n").write(r.stdout)
print(f"生成 {OUT.split(chr(92))[-1]}：{len(r.stdout)} 字节")
for line in r.stdout.split("\n"):
    if line.startswith(("+++", "@@", "+")):
        print("  " + line[:110])

shutil.rmtree(work, ignore_errors=True)
