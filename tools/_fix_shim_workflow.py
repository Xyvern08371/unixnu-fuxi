"""更新 shim workflow：打包不再传 dtb（fuxi 的 DTB 由 ABL 提供）。"""

import io

P = r"E:\ios-on-fuxi\.github\workflows\build-fuxi-shim.yml"
t = io.open(P, encoding="utf-8").read()

old = """          python3 tools/mkshim_bootimg.py \\
            --kernel loader-shim-fuxi/out-shim/Image \\
            --ramdisk rom/xnu/payload.bin \\
            --dtb rom/device/fuxi_runtime.dtb \\
            --output boot-fuxi-shim.img \\
            --cmdline "console=null\""""

new = """          python3 tools/mkshim_bootimg.py \\
            --kernel loader-shim-fuxi/out-shim/Image \\
            --ramdisk rom/xnu/payload.bin \\
            --output boot-fuxi-shim.img \\
            --cmdline "console=null\""""

if "--dtb" in t:
    t = t.replace(old, new, 1)
    io.open(P, "w", encoding="utf-8", newline="\n").write(t)
    print("workflow: 已去掉 --dtb")
else:
    print("workflow: 已经没有 --dtb")

for i, line in enumerate(io.open(P, encoding="utf-8").read().split("\n"), 1):
    if "mkshim_bootimg" in line or "--" in line and "kernel" in line or "ramdisk" in line or "output" in line:
        print("  L%d: %s" % (i, line.rstrip()))
