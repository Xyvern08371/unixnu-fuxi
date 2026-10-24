"""用 fuxi_early_* 直接写显存，打印 GICR 相关实参（这个阶段 fbcon 还没接管）。

pe_init_fiq 执行时 kprintf 只走串口（我们在屏幕上看到 panic 是因为 panic 走 fbcon），
所以要用 patch 0010 提供的早期帧缓冲输出：fuxi_early_string / fuxi_early_putc。
"""

import io
import os
import shutil
import subprocess
import tempfile

SRC = r"E:\download\xnu-src\pexpert\arm\pe_fiq.c"
PATCH = r"E:\ios-on-fuxi\xnu\patches\0004-fuxi-machine-config.patch"

work = tempfile.mkdtemp(prefix="gicr-early-")
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

text = io.open(PATCH, encoding="utf-8").read()
i = text.find("diff --git a/pexpert/arm/pe_fiq.c")
assert i >= 0
j = text.find("diff --git ", i + 10)
section = text[i:j if j > 0 else len(text)]

part = os.path.join(work, "cur.patch")
io.open(part, "w", encoding="utf-8", newline="\n").write(section)
run(["git", "apply", "-p1", part])
run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "cur"])

p = os.path.join(work, "pexpert", "arm", "pe_fiq.c")
src = io.open(p, encoding="utf-8").read()

# 1) 在 find_gicr_pe_base 之前加一个 hex 打印助手
anchor = "static vm_offset_t\nfind_gicr_pe_base()"
assert anchor in src
helper = """#if defined(ARM64_BOARD_CONFIG_FUXI)
extern void fuxi_early_putc(char c);
extern void fuxi_early_string(const char *s);

static void
fuxi_early_hex(uint64_t v)
{
	static const char digits[] = "0123456789abcdef";

	fuxi_early_string("0x");
	for (int i = 15; i >= 0; i--) {
		fuxi_early_putc(digits[(v >> (i * 4)) & 0xF]);
	}
	fuxi_early_putc('\\n');
}
#endif

"""
src = src.replace(anchor, helper + anchor, 1)

# 2) 把 kprintf 换成早期输出
old = """#if defined(ARM64_BOARD_CONFIG_FUXI)
	kprintf("FUXI GICR: gicd=%p gicr=%p size=%p pe=%p IGROUPR0=0x%x WAKER=0x%x\\n",
	    (void *)gicd_base, (void *)gicr_base, (void *)gicr_size, (void *)gicr_pe_base,
	    (unsigned)GICR_IGROUPR0, (unsigned)GICR_WAKER);
#endif"""
assert old in src, "kprintf 调试块没找到"

new = """#if defined(ARM64_BOARD_CONFIG_FUXI)
	fuxi_early_string("GICD ");
	fuxi_early_hex((uint64_t)gicd_base);
	fuxi_early_string("GICR ");
	fuxi_early_hex((uint64_t)gicr_base);
	fuxi_early_string("SIZE ");
	fuxi_early_hex((uint64_t)gicr_size);
	fuxi_early_string("PE   ");
	fuxi_early_hex((uint64_t)gicr_pe_base);
	fuxi_early_string("IGROUPR0 ");
	fuxi_early_hex((uint64_t)GICR_IGROUPR0);
	fuxi_early_string("WAKER ");
	fuxi_early_hex((uint64_t)GICR_WAKER);
#endif"""
src = src.replace(old, new, 1)

io.open(p, "w", encoding="utf-8", newline="\n").write(src)
run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "early-debug"])

r = run(["git", "diff", "HEAD~2", "HEAD", "--", "pexpert/arm/pe_fiq.c"])
new_sec = r.stdout
assert new_sec.strip()

io.open(PATCH, "w", encoding="utf-8", newline="\n").write(
    text[:i] + new_sec + (text[j:] if j > 0 else ""))

print("已改用早期帧缓冲输出打印 GICR 实参")
for line in new_sec.split("\n"):
    if "fuxi_early" in line or "GICR_IGROUPR0" in line:
        print("  " + line)

shutil.rmtree(work, ignore_errors=True)
