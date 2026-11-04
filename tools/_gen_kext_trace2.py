"""重新生成 0032：只在 OSKext.cpp 打点（libsa 的 bootstrap.cpp 没有 kprintf）。"""

import io
import os
import shutil
import subprocess
import tempfile

SRC = r"E:\download\xnu-src\libkern\c++\OSKext.cpp"
OUT = r"E:\ios-on-fuxi\xnu\patches\0032-fuxi-kext-trace.patch"

work = tempfile.mkdtemp(prefix="kexttrace2-")
os.makedirs(os.path.join(work, "libkern", "c++"), exist_ok=True)
target = os.path.join(work, "libkern", "c++", "OSKext.cpp")
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

# 1) 函数入口：打印条目数
a1 = """	/* locate the array of kext dictionaries */
	kextArray = OSDynamicCast(OSArray, infoDict->getObject(kPrelinkInfoDictionaryKey));
	if (!kextArray) {"""
assert a1 in t
r1 = """	/* locate the array of kext dictionaries */
	kextArray = OSDynamicCast(OSArray, infoDict->getObject(kPrelinkInfoDictionaryKey));
#if defined(ARM64_BOARD_CONFIG_FUXI)
	kprintf("FUXI PRELINK: kextArray=%s count=%u\\n",
	    kextArray ? "ok" : "null", kextArray ? (unsigned)kextArray->getCount() : 0);
#endif
	if (!kextArray) {"""
t = t.replace(a1, r1, 1)

# 2) 循环内：每条目的关键字段
a2 = """		withPrelinkedInfoDict(kextDict, (kaslrOffsets ? TRUE : FALSE), type);
"""
assert a2 in t
r2 = """#if defined(ARM64_BOARD_CONFIG_FUXI)
		{
			OSString *dbgIdent = OSDynamicCast(OSString,
			    kextDict->getObject(\"CFBundleIdentifier\"));
			OSNumber *dbgLoad = OSDynamicCast(OSNumber,
			    kextDict->getObject(\"_PrelinkExecutableLoadAddr\"));
			OSNumber *dbgSize = OSDynamicCast(OSNumber,
			    kextDict->getObject(\"_PrelinkExecutableSize\"));
			OSNumber *dbgKmod = OSDynamicCast(OSNumber,
			    kextDict->getObject(\"_PrelinkKmodInfo\"));
			kprintf(\"FUXI KEXT %d: %s load=0x%llx size=%llu kmod=0x%llx\\n\", i,
			    dbgIdent ? dbgIdent->getCStringNoCopy() : \"(null)\",
			    dbgLoad ? (unsigned long long)dbgLoad->unsigned64BitValue() : 0ULL,
			    dbgSize ? (unsigned long long)dbgSize->unsigned64BitValue() : 0ULL,
			    dbgKmod ? (unsigned long long)dbgKmod->unsigned64BitValue() : 0ULL);
		}
#endif
		withPrelinkedInfoDict(kextDict, (kaslrOffsets ? TRUE : FALSE), type);
#if defined(ARM64_BOARD_CONFIG_FUXI)
		kprintf(\"FUXI KEXT %d: done\\n\", i);
#endif
"""
t = t.replace(a2, r2, 1)

# 3) 循环后
a3 = """	if (kaslrOffsets && vm_kernel_slide > 0) {"""
assert a3 in t
r3 = """#if defined(ARM64_BOARD_CONFIG_FUXI)
	kprintf(\"FUXI PRELINK: loop finished\\n\");
#endif
	if (kaslrOffsets && vm_kernel_slide > 0) {"""
t = t.replace(a3, r3, 1)

io.open(target, "w", encoding="utf-8", newline="\n").write(t)
run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "trace2"])

r = run(["git", "diff", "HEAD~1", "HEAD"])
io.open(OUT, "w", encoding="utf-8", newline="\n").write(r.stdout)
print(f"生成 {OUT.split(chr(92))[-1]}：{len(r.stdout)} 字节")
for line in r.stdout.split("\n"):
    if line.startswith(("+	kprintf", "@@")):
        print("  " + line[:110])

shutil.rmtree(work, ignore_errors=True)
