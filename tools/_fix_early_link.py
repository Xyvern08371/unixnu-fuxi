"""修链接错误：fuxi_early_string 是 static，改为用导出的 fuxi_early_putc 自己拼。"""

import io
import os
import shutil
import subprocess
import tempfile

SRC = r"E:\download\xnu-src\pexpert\arm\pe_fiq.c"
PATCH = r"E:\ios-on-fuxi\xnu\patches\0004-fuxi-machine-config.patch"

work = tempfile.mkdtemp(prefix="fix-link-")
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

# 1) 去掉对 static 函数的 extern 声明，换成自己的 puts
src = src.replace(
    "extern void fuxi_early_putc(char c);\nextern void fuxi_early_string(const char *s);",
    """extern void fuxi_early_putc(char c);

static void
fuxi_early_puts(const char *s)
{
	while (*s) {
		fuxi_early_putc(*s++);
	}
}""")

# 2) 所有 fuxi_early_string( -> fuxi_early_puts(
src = src.replace("fuxi_early_string(", "fuxi_early_puts(")

assert "fuxi_early_string" not in src, "还有残留的 fuxi_early_string"
io.open(p, "w", encoding="utf-8", newline="\n").write(src)
run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "fix-link"])

r = run(["git", "diff", "HEAD~2", "HEAD", "--", "pexpert/arm/pe_fiq.c"])
new_sec = r.stdout
assert new_sec.strip()

io.open(PATCH, "w", encoding="utf-8", newline="\n").write(
    text[:i] + new_sec + (text[j:] if j > 0 else ""))

print("已修：改用 fuxi_early_putc 自己实现 puts")
for line in new_sec.split("\n"):
    if "fuxi_early_puts" in line or "fuxi_early_putc" in line:
        print("  " + line)

shutil.rmtree(work, ignore_errors=True)
