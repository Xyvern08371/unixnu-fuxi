"""shim workflow：打包时把 DTB 一起塞进 kernel 段（否则 ABL 拒绝启动）。"""

import io

W = r"E:\ios-on-fuxi\.github\workflows\build-fuxi-shim.yml"
w = io.open(W, encoding="utf-8").read()

if "--dtb" not in w:
    old = """          python3 tools/mkshim_bootimg.py \\
            --kernel loader-shim-fuxi/out-shim/Image.gz \\
            --output boot-fuxi-shim.img \\
            --cmdline "console=null\""""
    new = """          python3 tools/mkshim_bootimg.py \\
            --kernel loader-shim-fuxi/out-shim/Image.gz \\
            --dtb rom/device/fuxi_runtime.dtb \\
            --output boot-fuxi-shim.img"""
    if old in w:
        w = w.replace(old, new, 1)
    else:
        # 没有 --cmdline 的版本
        old2 = """          python3 tools/mkshim_bootimg.py \\
            --kernel loader-shim-fuxi/out-shim/Image.gz \\
            --output boot-fuxi-shim.img"""
        new2 = """          python3 tools/mkshim_bootimg.py \\
            --kernel loader-shim-fuxi/out-shim/Image.gz \\
            --dtb rom/device/fuxi_runtime.dtb \\
            --output boot-fuxi-shim.img"""
        assert old2 in w, "打包步骤没找到"
        w = w.replace(old2, new2, 1)
    io.open(W, "w", encoding="utf-8", newline="\n").write(w)
    print("workflow: 打包时带上 DTB")
else:
    print("workflow: 已经带 DTB")

for i, line in enumerate(io.open(W, encoding="utf-8").read().split("\n"), 1):
    if "mkshim_bootimg" in line or "--dtb" in line or "--kernel" in line or "--output" in line:
        print("  L%d: %s" % (i, line.rstrip()))
