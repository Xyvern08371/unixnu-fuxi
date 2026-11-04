"""生成 0032：在 kext 加载路径上打点，定位 zone_require_ro panic 的来源。"""

import io
import os
import shutil
import subprocess
import tempfile

FILES = [
    (r"E:\download\xnu-src\libkern\c++\OSKext.cpp", "libkern/c++/OSKext.cpp"),
    (r"E:\download\xnu-src\libsa\bootstrap.cpp", "libsa/bootstrap.cpp"),
]
OUT = r"E:\ios-on-fuxi\xnu\patches\0032-fuxi-kext-trace.patch"

work = tempfile.mkdtemp(prefix="kexttrace-")
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

# ---- OSKext.cpp：循环里逐个打印 ----
p = os.path.join(work, "libkern", "c++", "OSKext.cpp")
t = io.open(p, encoding="utf-8").read()
anchor = """		withPrelinkedInfoDict(kextDict, (kaslrOffsets ? TRUE : FALSE), type);
"""
assert anchor in t
add = """#if defined(ARM64_BOARD_CONFIG_FUXI)
		{
			OSString *dbgIdent = OSDynamicCast(OSString,
			    kextDict->getObject("CFBundleIdentifier"));
			OSNumber *dbgLoad = OSDynamicCast(OSNumber,
			    kextDict->getObject("_PrelinkExecutableLoadAddr"));
			OSNumber *dbgSize = OSDynamicCast(OSNumber,
			    kextDict->getObject("_PrelinkExecutableSize"));
			OSNumber *dbgKmod = OSDynamicCast(OSNumber,
			    kextDict->getObject("_PrelinkKmodInfo"));
			kprintf("FUXI KEXT %d/%u: %s load=0x%llx size=%llu kmod=0x%llx\\n", i,
			    (unsigned)kextArray->getCount(),
			    dbgIdent ? dbgIdent->getCStringNoCopy() : "(null)",
			    dbgLoad ? dbgLoad->unsigned64BitValue() : 0ULL,
			    dbgSize ? dbgSize->unsigned64BitValue() : 0ULL,
			    dbgKmod ? dbgKmod->unsigned64BitValue() : 0ULL);
		}
#endif
		withPrelinkedInfoDict(kextDict, (kaslrOffsets ? TRUE : FALSE), type);
#if defined(ARM64_BOARD_CONFIG_FUXI)
		kprintf("FUXI KEXT %d: done\\n", i);
#endif
"""
t = t.replace(anchor, add, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(t)

# ---- bootstrap.cpp：打印 info section 大小与解析结果 ----
q = os.path.join(work, "libsa", "bootstrap.cpp")
b = io.open(q, encoding="utf-8").read()
a1 = """	prelinkInfoSect = getsectbynamefromheader(mh, kPrelinkInfoSegment, kPrelinkInfoSection);
	if (prelinkInfoSect->size) {"""
assert a1 in b
r1 = """	prelinkInfoSect = getsectbynamefromheader(mh, kPrelinkInfoSegment, kPrelinkInfoSection);
#if defined(ARM64_BOARD_CONFIG_FUXI)
	kprintf("FUXI PRELINK: info section addr=0x%llx size=%llu\\n",
	    (unsigned long long)prelinkInfoSect->addr,
	    (unsigned long long)prelinkInfoSect->size);
#endif
	if (prelinkInfoSect->size) {"""
b = b.replace(a1, r1, 1)

a2 = """	parsedXML = OSUnserializeXML((const char *)infoPlistSection->addr, errorString);"""
assert a2 in b
r2 = """#if defined(ARM64_BOARD_CONFIG_FUXI)
	kprintf("FUXI PRELINK: parsing XML at 0x%llx size=%llu\\n",
	    (unsigned long long)infoPlistSection->addr,
	    (unsigned long long)infoPlistSection->size);
#endif
	parsedXML = OSUnserializeXML((const char *)infoPlistSection->addr, errorString);
#if defined(ARM64_BOARD_CONFIG_FUXI)
	kprintf("FUXI PRELINK: parsed=%d\\n", parsedXML ? 1 : 0);
#endif"""
b = b.replace(a2, r2, 1)

a3 = """	ret = OSKext::addKextsFromKextCollection(mh, infoDict,
	    kPrelinkTextSegment, loaded_kcUUID, (mh->filetype == MH_FILESET) ? type : KCKindUnknown);"""
assert a3 in b
r3 = a3 + """
#if defined(ARM64_BOARD_CONFIG_FUXI)
	kprintf("FUXI PRELINK: addKextsFromKextCollection ret=%d\\n", ret);
#endif"""
b = b.replace(a3, r3, 1)
io.open(q, "w", encoding="utf-8", newline="\n").write(b)

run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "trace"])
r = run(["git", "diff", "HEAD~1", "HEAD"])
io.open(OUT, "w", encoding="utf-8", newline="\n").write(r.stdout)
print(f"生成 {OUT.split(chr(92))[-1]}：{len(r.stdout)} 字节")
for line in r.stdout.split("\n"):
    if line.startswith(("+++", "@@", "+	kprintf", "+		{")):
        print("  " + line[:110])

shutil.rmtree(work, ignore_errors=True)
