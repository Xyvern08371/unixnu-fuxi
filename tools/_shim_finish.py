"""收尾：补 loader.c 的声明、改 ramdisk 地址、CI 传 PAYLOAD_FILE、去掉 --ramdisk。"""

import io

# 1) loader.c: 补 g_payload_ptr 声明
L = r"E:\ios-on-fuxi\loader-shim-fuxi\loader.c"
t = io.open(L, encoding="utf-8").read()
if "extern const void *g_payload_ptr;" not in t:
    anchor = "const char *loader_boot(uintptr_t dtb)"
    assert anchor in t
    t = t.replace(anchor, "extern const void *g_payload_ptr;\n\n" + anchor, 1)
    io.open(L, "w", encoding="utf-8", newline="\n").write(t)
    print("loader.c: +extern g_payload_ptr")

# 2) packer: ramdisk 地址对齐 UEFI 镜像（0x10000000）
M = r"E:\ios-on-fuxi\tools\mkshim_bootimg.py"
m = io.open(M, encoding="utf-8").read()
m = m.replace("RAMDISK_ADDR = 0x20000000", "RAMDISK_ADDR = 0x10000000")
io.open(M, "w", encoding="utf-8", newline="\n").write(m)
print("mkshim_bootimg.py: ramdisk_addr -> 0x10000000（与 UEFI 镜像一致）")

# 3) workflow: 编译时传 PAYLOAD_FILE，打包不再传 --ramdisk
W = r"E:\ios-on-fuxi\.github\workflows\build-fuxi-shim.yml"
w = io.open(W, encoding="utf-8").read()

# 先生成 payload，再编译 shim（顺序很重要：payload 要内嵌）
if "PAYLOAD_FILE" not in w:
    old_build = w[w.find("      - name: 编译 shim"):w.find("      - name: 生成 XNU payload（ADT + 段表）")]
    new_build = """      - name: 生成 XNU payload（ADT + 段表）
        run: |
          set -x
          python3 tools/adt_fix_fuxi.py rom/xnu/kalama.adt rom/xnu/fuxi.adt
          python3 tools/mkpayload_fuxi.py rom/xnu/kernel.development.fuxi rom/xnu/fuxi.adt rom/xnu/payload.bin \\
            --cmdline "debug=0xc serial=3 cpus=1 keepsyms=1 -v"
          ls -l rom/xnu/payload.bin

      - name: 编译 shim（内嵌 payload）
        run: |
          chmod +x loader-shim-fuxi/build-shim.sh
          PAYLOAD_FILE=../rom/xnu/payload.bin bash loader-shim-fuxi/build-shim.sh 2>&1 | tee shim-build.log
          ls -l loader-shim-fuxi/out-shim/Image

"""
    w = w.replace(old_build, new_build, 1)

    # 去掉原来的「生成 payload」步骤和打包里的 --ramdisk
    start = w.find("      - name: 生成 XNU payload（ADT + 段表）")
    second = w.find("      - name: 生成 XNU payload（ADT + 段表）", start + 10)
    if second > 0:
        end = w.find("      - name: 打包 boot.img", second)
        w = w[:second] + w[end:]

    w = w.replace("""            --ramdisk rom/xnu/payload.bin \\
""", "")
    io.open(W, "w", encoding="utf-8", newline="\n").write(w)
    print("workflow: 顺序改为 payload → shim(内嵌) → boot.img")

print("\n=== workflow 步骤顺序 ===")
for i, line in enumerate(io.open(W, encoding="utf-8").read().split("\n"), 1):
    if line.strip().startswith("- name:"):
        print("  L%d: %s" % (i, line.strip()))
