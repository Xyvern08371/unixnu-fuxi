"""生成 0036：TPIDR_EL1==0 时让 ml_get_timebase/ml_get_hwclock 直接返回 0。

背景：真机/裸机环境下内核在 machine_set_current_thread() 之前就调用
ml_get_timebase()，此时 TPIDR_EL1 还是 0，getCpuDatap() 解引用 NULL
（读 [0+0x228]）触发同步异常，随后异常处理链自身也崩（读 [0+0x220]），
什么都看不到。

iBoot 交棒前会先把 TPIDR_EL1 设好，所以 Apple 的平台不会遇到这个问题。
这里给 fuxi 加一个保护：per-CPU 数据尚未建立时返回 0，让内核继续往下走。
"""

import io
import os
import shutil
import subprocess
import tempfile

SRC = r"E:\download\xnu-src\osfmk\arm64\machine_routines.c"
OUT = r"E:\ios-on-fuxi\xnu\patches\0036-fuxi-timebase-before-percpu.patch"

work = tempfile.mkdtemp(prefix="tb-")
os.makedirs(os.path.join(work, "osfmk", "arm64"), exist_ok=True)
target = os.path.join(work, "osfmk", "arm64", "machine_routines.c")
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

GUARD = """#if defined(ARM64_BOARD_CONFIG_FUXI)
	{
		uint64_t fuxi_tpidr;

		/* per-CPU 数据尚未建立（machine_set_current_thread 还没跑）：
		 * 读 cpu_base_timebase 会解引用 NULL。返回 0 让内核继续。 */
		__asm__ volatile("mrs %0, tpidr_el1" : "=r"(fuxi_tpidr));
		if (fuxi_tpidr == 0) {
			return 0;
		}
	}
#endif
"""

# 1) ml_get_timebase
a1 = """uint64_t
ml_get_timebase()
{
	uint64_t clock, timebase;
"""
assert a1 in t, "ml_get_timebase 锚点没找到"
t = t.replace(a1, a1 + "\n" + GUARD, 1)

# 2) ml_get_hwclock
a2 = """ml_get_hwclock()
{
	uint64_t timebase = nonspeculative_timebase();
"""
assert a2 in t, "ml_get_hwclock 锚点没找到"
t = t.replace(a2, a2 + "\n" + GUARD, 1)

io.open(target, "w", encoding="utf-8", newline="\n").write(t)
run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "guard"])
r = run(["git", "diff", "HEAD~1", "HEAD"])
io.open(OUT, "w", encoding="utf-8", newline="\n").write(r.stdout)
print(f"生成 {OUT.split(chr(92))[-1]}：{len(r.stdout)} 字节")
for line in r.stdout.split("\n"):
    if line.startswith(("+++", "@@", "+", "-")):
        print("  " + line[:110])

shutil.rmtree(work, ignore_errors=True)
