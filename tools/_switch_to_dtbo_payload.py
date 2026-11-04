import io

W = r"E:\ios-on-fuxi\.github\workflows\build-fuxi-uefi.yml"
t = io.open(W, encoding="utf-8").read()
lines = t.split("\n")

# 1) 开关回到 on（payload 仍然要生成，只是不再嵌进 EFI）
lines = [l.replace('PAYLOAD_ENABLED: "off"', 'PAYLOAD_ENABLED: "on"') for l in lines]
t = "\n".join(lines)

# 2) 把 "生成 .incbin 汇编" 那段换成 "生成可刷进 dtbo 的镜像"
old_block = """          if [ -f rom/xnu/payload.bin ]; then
            echo "=== 生成 .incbin 汇编 ==="
            {
              echo '.section .rodata'
              echo '.global gXnuPayload'
              echo '.global gXnuPayloadEnd'
              echo '.align 12'
              echo 'gXnuPayload:'
              echo ".incbin \\"$PWD/rom/xnu/payload.bin\\""
              echo 'gXnuPayloadEnd:'
            } > loader/xnu_payload.S
            cat loader/xnu_payload.S
          else
            echo "没有 payload.bin，保持占位 .S（固件里不带 XNU）"
          fi"""
new_block = """          if [ -f rom/xnu/payload.bin ]; then
            echo "=== 生成可刷进 dtbo 的镜像（不嵌进 EFI）==="
            python3 tools/mkpayload_img.py rom/xnu/payload.bin rom/xnu/payload-blob.img
            ls -l rom/xnu/payload-blob.img
          else
            echo "没有 payload.bin"
          fi"""
assert old_block in t, "incbin 段没找到"
t = t.replace(old_block, new_block)

# 3) 注入探针时加上 XnuLoad.c
t = t.replace(
    "             loader/XnuBoot.c loader/xnu_jump.S loader/xnu_payload.S \"$probe\"/",
    "             loader/XnuBoot.c loader/XnuLoad.c loader/xnu_jump.S loader/xnu_payload.S \"$probe\"/",
)

# 4) 产物里加 payload-blob.img
if "            payload-blob.img" not in t:
    t = t.replace("            build.log\n", "            build.log\n            rom/xnu/payload-blob.img\n")

io.open(W, "w", encoding="utf-8", newline="\n").write(t)

lines = t.split("\n")
bad = [i for i, l in enumerate(lines, 1) if not l.strip().startswith("#") and l.count('"') % 2]
print("引号不配对:", bad[:5] if bad else "无")
print("PAYLOAD_ENABLED:", [l.strip() for l in lines if "PAYLOAD_ENABLED:" in l])
print("XnuLoad.c:", sum("XnuLoad.c" in l for l in lines))
print("payload-blob:", sum("payload-blob" in l for l in lines))
