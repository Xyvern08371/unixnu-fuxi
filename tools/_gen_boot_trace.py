"""生成 0028：在 kernel_bootstrap 的每个关键步骤前后打印进度。

目的：定位 kdp_core 之后（bsd_init 之前）到底卡在哪一步。
最可疑的是 initialize_screen()——它会等 IOKit 提供 framebuffer 服务。
"""

import io
import os
import shutil
import subprocess
import tempfile

SRC = r"E:\download\xnu-src\osfmk\kern\startup.c"
OUT = r"E:\ios-on-fuxi\xnu\patches\0028-fuxi-boot-trace.patch"

work = tempfile.mkdtemp(prefix="boottrace-")
os.makedirs(os.path.join(work, "osfmk", "kern"), exist_ok=True)
target = os.path.join(work, "osfmk", "kern", "startup.c")
shutil.copy2(SRC, target)

src = io.open(target, encoding="utf-8").read()

TRACE = '\tkprintf("FUXI BOOT: %s\\n", "%s");'

# (锚点整行, 打印文本, 插在锚点前还是后)
steps = [
    ("\tkdp_init();", "kdp_init done", "after"),
    ("\t\tkernel_bootstrap_log(\"hv_support_init\");", "before hv_support_init", "before"),
    ("\t\tbootprofile_init();", "bootprofile_init done", "after"),
    ("\tkernel_startup_initialize_upto(STARTUP_SUB_SYSCTL);", "SYSCTL phase done", "after"),
    ("\tPE_init_iokit();", "PE_init_iokit done", "after"),
    ("\tkernel_startup_initialize_upto(STARTUP_SUB_EARLY_BOOT);", "EARLY_BOOT phase done", "after"),
    ("\tinitialize_screen(NULL, kPEAcquireScreen);", "initialize_screen done", "after"),
    ("\tvm_commpage_init();", "before commpage_init", "before"),
    ("\t\tload_static_trust_cache();", "trust cache done", "after"),
    ("\tkernel_startup_initialize_upto(STARTUP_SUB_LOCKDOWN);", "LOCKDOWN phase done", "after"),
    ("\tOSKextRemoveKextBootstrap();", "kext bootstrap removed", "after"),
    ("\tmachine_lockdown();", "machine_lockdown done", "after"),
    ("\tPE_lockdown_iokit();", "PE_lockdown_iokit done", "after"),
    ("\tbsd_init();", "entering bsd_init", "before"),
]

added = 0
for anchor, label, where in steps:
    if anchor not in src:
        print(f"  ⚠ 锚点缺失: {anchor.strip()}")
        continue
    line = '\tkprintf("FUXI BOOT: %s\\n");' % label
    if where == "after":
        src = src.replace(anchor, anchor + "\n" + line, 1)
    else:
        # 保留原缩进
        indent = anchor[:len(anchor) - len(anchor.lstrip("\t"))]
        src = src.replace(anchor, indent + line.strip() + "\n" + anchor, 1)
    added += 1

io.open(target, "w", encoding="utf-8", newline="\n").write(src)
print(f"插入 {added} 个进度打印")

r = subprocess.run(["git", "init", "-q", "."], cwd=work, capture_output=True)
# 用原始文件建基线，再 diff
base_dir = tempfile.mkdtemp(prefix="boottrace-base-")
os.makedirs(os.path.join(base_dir, "osfmk", "kern"), exist_ok=True)
shutil.copy2(SRC, os.path.join(base_dir, "osfmk", "kern", "startup.c"))

r = subprocess.run(["git", "diff", "--no-index", "--src-prefix=a/", "--dst-prefix=b/",
                    os.path.join(base_dir, "osfmk", "kern", "startup.c"), target],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
diff = r.stdout
# 修正路径为仓库相对路径
diff = diff.replace(os.path.join(base_dir, "osfmk", "kern", "startup.c").replace("\\", "/"), "osfmk/kern/startup.c")
diff = diff.replace(target.replace("\\", "/"), "osfmk/kern/startup.c")
diff = diff.replace("--- a/" + os.path.join(base_dir, "osfmk", "kern", "startup.c").replace("\\", "/"), "--- a/osfmk/kern/startup.c")
diff = diff.replace("+++ b/" + target.replace("\\", "/"), "+++ b/osfmk/kern/startup.c")

if "diff --git" not in diff:
    diff = "diff --git a/osfmk/kern/startup.c b/osfmk/kern/startup.c\n" + diff

io.open(OUT, "w", encoding="utf-8", newline="\n").write(diff)
print(f"生成 {OUT.split(chr(92))[-1]}：{len(diff)} 字节")

shutil.rmtree(work, ignore_errors=True)
shutil.rmtree(base_dir, ignore_errors=True)

print()
print("=== 补丁片段预览 ===")
for line in diff.split("\n")[:14]:
    print("  " + line)
