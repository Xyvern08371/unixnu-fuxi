"""shim 的 kernel 段改成 gzip（和能启动的 UEFI 镜像一致）。"""

import io

W = r"E:\ios-on-fuxi\.github\workflows\build-fuxi-shim.yml"
w = io.open(W, encoding="utf-8").read()

if "gzip -9" not in w:
    old = """          python3 tools/mkshim_bootimg.py \\
            --kernel loader-shim-fuxi/out-shim/Image \\"""
    new = """          gzip -9 -c loader-shim-fuxi/out-shim/Image > loader-shim-fuxi/out-shim/Image.gz
          ls -l loader-shim-fuxi/out-shim/Image.gz
          python3 tools/mkshim_bootimg.py \\
            --kernel loader-shim-fuxi/out-shim/Image.gz \\"""
    assert old in w, "pack step not found"
    w = w.replace(old, new, 1)
    io.open(W, "w", encoding="utf-8", newline="\n").write(w)
    print("workflow: kernel 改成 Image.gz")
else:
    print("已经用 gzip 了")

for i, line in enumerate(io.open(W, encoding="utf-8").read().split("\n"), 1):
    if "gzip" in line or "--kernel" in line:
        print("  L%d: %s" % (i, line.strip()))
