"""生成 0030：为 fuxi 扩大 kext 预链接区。

现状：
  ARM64_PLKSEG_ADDR = 0xfffffe0004004000   (__PRELINK_TEXT 占位)
  ARM64_LINK_ADDR   = 0xfffffe0007004000   (内核 __TEXT)

  virt_base = __TEXT 所在 32MB 块的基址 = 0xfffffe0006000000，
  可用的 kext 区 = [0x6000000, 0x7004000) ≈ 16MB —— 装不下 APFS 组件集（约 19.4MB）。

做法：把 __TEXT 抬到 0xfffffe0009f04000。
  virt_base 随之变为 0xfffffe0008000000，
  kext 区 = [0x8000000, 0x9f04000) ≈ 31MB。
"""

import io
import os
import shutil
import subprocess
import tempfile

SRC = r"E:\download\xnu-src\makedefs\MakeInc.def"
OUT = r"E:\ios-on-fuxi\xnu\patches\0030-fuxi-kext-region.patch"

work = tempfile.mkdtemp(prefix="kextregion-")
os.makedirs(os.path.join(work, "makedefs"), exist_ok=True)
target = os.path.join(work, "makedefs", "MakeInc.def")
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

anchor = """# Use ARM_LARGE_MEMORY config for all MacOSX targets.
ifneq ($(filter $(PLATFORM),MacOSX),)
LARGE_MEMORY_DEFINE=-DARM_LARGE_MEMORY=1
ARM64_PLKSEG_ADDR  =0xfffffe0004004000
ARM64_LINK_ADDR    =0xfffffe0007004000
endif
"""
assert anchor in t, "MakeInc.def 锚点没找到"

add = anchor + """
# FUXI: prelinked kexts need more room than the 16MB between virt_base and __TEXT.
# Raising __TEXT to the top of the next 32MB block moves virt_base to
# 0xfffffe0008000000 and grows the kext region to ~31MB.
ifneq ($(filter FUXI,$(CURRENT_MACHINE_CONFIG)),)
ARM64_LINK_ADDR    =0xfffffe0009f04000
endif
"""
t = t.replace(anchor, add, 1)
io.open(target, "w", encoding="utf-8", newline="\n").write(t)
run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "fuxi-kext-region"])

r = run(["git", "diff", "HEAD~1", "HEAD"])
diff = r.stdout
io.open(OUT, "w", encoding="utf-8", newline="\n").write(diff)
print(f"生成 {OUT.split(chr(92))[-1]}：{len(diff)} 字节")
print()
for line in diff.split("\n"):
    print("  " + line)

shutil.rmtree(work, ignore_errors=True)
