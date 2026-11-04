"""生成 0029：为 Apple 16.7 内核 kext 补上 vfs_getvfs_with_vfsops 兼容符号。

背景：APFS kext（来自 xnu-8796.142 的 kernelcache）导入这个符号，
而我们的源码树是 8796.101.5，还没有它。语义上它等价于
"按 fsid 找 mount，但要求 vfsops 匹配"。
"""

import io
import os
import shutil
import subprocess
import tempfile

SRC_VFS = r"E:\download\xnu-src\bsd\vfs\vfs_subr.c"
SRC_HDR = r"E:\download\xnu-src\bsd\sys\mount.h"
OUT = r"E:\ios-on-fuxi\xnu\patches\0029-fuxi-prelink-compat.patch"

work = tempfile.mkdtemp(prefix="compat-")
os.makedirs(os.path.join(work, "bsd", "vfs"), exist_ok=True)
os.makedirs(os.path.join(work, "bsd", "sys"), exist_ok=True)
vfs = os.path.join(work, "bsd", "vfs", "vfs_subr.c")
hdr = os.path.join(work, "bsd", "sys", "mount.h")
shutil.copy2(SRC_VFS, vfs)
shutil.copy2(SRC_HDR, hdr)


def run(cmd, check=True):
    r = subprocess.run(cmd, cwd=work, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        print("失败:", " ".join(cmd))
        print(r.stdout[-500:], r.stderr[-500:])
        raise SystemExit(1)
    return r


run(["git", "init", "-q", "."])
run(["git", "add", "-A"])
run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base"])

# --- vfs_subr.c：在 vfs_getvfs 之后加兼容实现 ---
t = io.open(vfs, encoding="utf-8").read()
anchor = """struct mount *
vfs_getvfs(fsid_t *fsid)
{
	return mount_list_lookupby_fsid(fsid, 0, 0);
}
"""
assert anchor in t, "vfs_getvfs 锚点没找到"
add = anchor + """
/*
 * fuxi: iOS 16.7 kernelcache 里的 kext（xnu-8796.142 构建）导入此符号，
 * 而我们的源码树（8796.101.5）还没有它。语义：按 fsid 找挂载点，
 * 但要求它的 vfsops 与调用者期望的一致。
 */
struct mount *
vfs_getvfs_with_vfsops(fsid_t *fsid, const struct vfsops *vfsops)
{
	struct mount *mp = vfs_getvfs(fsid);

	if (mp != NULL && mp->mnt_op != vfsops) {
		mp = NULL;
	}
	return mp;
}
"""
t = t.replace(anchor, add, 1)
io.open(vfs, "w", encoding="utf-8", newline="\n").write(t)

# --- mount.h：加原型 ---
h = io.open(hdr, encoding="utf-8").read()
anchor_h = "mount_t vfs_getvfs(fsid_t *fsid);"
assert anchor_h in h, "mount.h 锚点没找到"
h = h.replace(anchor_h, anchor_h + """

/* fuxi: 供 iOS 16.7 kernelcache kext 使用的兼容接口 */
struct mount *vfs_getvfs_with_vfsops(fsid_t *fsid, const struct vfsops *vfsops);""", 1)
io.open(hdr, "w", encoding="utf-8", newline="\n").write(h)

run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "compat"])

r = run(["git", "diff", "HEAD~1", "HEAD"])
diff = r.stdout

# 修一下 diff 头（git diff 在临时仓库里路径是 a/bsd/...，正好能用）
io.open(OUT, "w", encoding="utf-8", newline="\n").write(diff)
print(f"生成 {OUT.split(chr(92))[-1]}：{len(diff)} 字节")
print()
for line in diff.split("\n")[:16]:
    print("  " + line)

shutil.rmtree(work, ignore_errors=True)
