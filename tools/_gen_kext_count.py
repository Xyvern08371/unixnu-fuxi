"""生成 0031：确认预链接 kext 是否被内核识别。"""

import io
import os
import shutil
import subprocess
import tempfile

SRC = r"E:\download\xnu-src\libkern\c++\OSKext.cpp"
OUT = r"E:\ios-on-fuxi\xnu\patches\0031-fuxi-kext-count.patch"

work = tempfile.mkdtemp(prefix="kextcount-")
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

anchor = """		withPrelinkedInfoDict(kextDict, (kaslrOffsets ? TRUE : FALSE), type);
	}
"""
assert anchor in t, "锚点没找到"

add = anchor + """
#if defined(ARM64_BOARD_CONFIG_FUXI)
	{
		int apfs = 0, sbd = 0;
		for (int i = 0; i < (int)kextArray->getCount(); ++i) {
			OSDictionary *d = OSDynamicCast(OSDictionary, kextArray->getObject(i));
			if (!d) {
				continue;
			}
			OSString *ident = OSDynamicCast(OSString, d->getObject("CFBundleIdentifier"));
			if (!ident) {
				continue;
			}
			if (!strcmp(ident->getCStringNoCopy(), "com.apple.filesystems.apfs")) {
				apfs++;
			}
			if (!strcmp(ident->getCStringNoCopy(), "com.apple.security.sandbox")) {
				sbd++;
			}
		}
		kprintf("FUXI KEXT: %u prelinked entries (apfs=%d sandbox=%d)\\n",
		    kextArray->getCount(), apfs, sbd);
	}
#endif
"""
t = t.replace(anchor, add, 1)
io.open(target, "w", encoding="utf-8", newline="\n").write(t)
run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "kext count"])

r = run(["git", "diff", "HEAD~1", "HEAD"])
io.open(OUT, "w", encoding="utf-8", newline="\n").write(r.stdout)
print(f"生成 {OUT.split(chr(92))[-1]}：{len(r.stdout)} 字节")
for line in r.stdout.split("\n")[:30]:
    print("  " + line)

shutil.rmtree(work, ignore_errors=True)
