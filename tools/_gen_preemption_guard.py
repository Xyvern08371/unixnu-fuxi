"""生成 0039：current_thread() 为 NULL 时 get_preemption_level 返回 0。

0036 已经让 ml_get_timebase/ml_get_hwclock 在 TPIDR==0 时返回 0，
剩下的第一处崩溃是 get_preemption_level（FAR=0x230）：
    get_preemption_level() -> get_preemption_level_for_thread(current_thread())
current_thread() 读 TPIDR_EL1，arm_init 早期为 0 -> NULL -> 解引用 NULL。

加锁路径都会走 get_preemption_level，在这里挡一次比逐个改调用点省事。
"""

import io
import os
import shutil
import subprocess
import tempfile

SRC = r"E:\download\xnu-src\osfmk\arm\locks_arm.c"
OUT = r"E:\ios-on-fuxi\xnu\patches\0039-fuxi-preemption-before-thread.patch"

work = tempfile.mkdtemp(prefix="pl-")
os.makedirs(os.path.join(work, "osfmk", "arm"), exist_ok=True)
target = os.path.join(work, "osfmk", "arm", "locks_arm.c")
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

anchor = """__attribute__((always_inline))
int
get_preemption_level(void)
{
	return get_preemption_level_for_thread(current_thread());
}
"""
assert anchor in t, "get_preemption_level 锚点没找到"

new = """__attribute__((always_inline))
int
get_preemption_level(void)
{
#if defined(ARM64_BOARD_CONFIG_FUXI)
	thread_t self = current_thread();

	/*
	 * arm_init 早期（PE_init_platform 内部加锁）TPIDR_EL1 还是 0，
	 * current_thread() 返回 NULL，解引用 [NULL+0x230] 会触发同步异常。
	 * 这个时序点上还没有任何真实线程，抢占层级就是 0。
	 */
	if (self == NULL) {
		return 0;
	}
	return get_preemption_level_for_thread(self);
#else
	return get_preemption_level_for_thread(current_thread());
#endif
}
"""
t = t.replace(anchor, new, 1)
io.open(target, "w", encoding="utf-8", newline="\n").write(t)

run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "guard"])
r = run(["git", "diff", "HEAD~1", "HEAD"])
io.open(OUT, "w", encoding="utf-8", newline="\n").write(r.stdout)
print(f"生成 {OUT.split(chr(92))[-1]}：{len(r.stdout)} 字节")
for line in r.stdout.split("\n"):
    if line.startswith(("+++", "@@", "+", "-")):
        print("  " + line[:110])

shutil.rmtree(work, ignore_errors=True)
