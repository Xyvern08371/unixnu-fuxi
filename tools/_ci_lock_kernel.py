"""CI：固件优先使用仓库里锁定的内核，避免 API 取到旧提交的产物。"""

import io

P = r"E:\ios-on-fuxi\.github\workflows\build-fuxi-uefi.yml"
t = io.open(P, encoding="utf-8").read()

if "不查 API" not in t:
    marker = '          echo "=== 找最新的 xnu-kernel 产物 ==="'
    assert marker in t, "锚点没找到"

    block = '''          # 优先用仓库里锁定的内核：API 取"最新产物"会拿到旧提交的结果
          # （新提交构建失败时，"最新成功产物"就是旧的），导致固件里的内核
          # 和本地测试的内核不是同一个。锁定文件就没这个问题。
          if [ -f rom/xnu/kernel.development.fuxi ]; then
            echo "=== 用仓库里锁定的内核（不查 API）==="
            KERNEL=rom/xnu/kernel.development.fuxi
            ART=local
          else
''' + marker

    t = t.replace(marker, block, 1)

    anchor = '          if [ "$ART" != local ]; then'
    assert anchor in t, "ART 锚点没找到"
    t = t.replace(anchor, "          fi\n\n" + anchor, 1)

    old2 = '          echo "kernel: [$KERNEL]"'
    assert old2 in t
    new2 = '''          echo "kernel: [$KERNEL]"
          if [ -f "$KERNEL" ]; then
            echo "内核指纹: $(stat -c%s "$KERNEL") 字节  sha256=$(sha256sum "$KERNEL" | cut -c1-16)"
          fi'''
    t = t.replace(old2, new2, 1)

    io.open(P, "w", encoding="utf-8", newline="\n").write(t)
    print("已改为优先用锁定内核 + 打印指纹")
else:
    print("已经是锁定内核逻辑，跳过")

lines = t.split("\n")
bad = [i for i, l in enumerate(lines, 1) if not l.strip().startswith("#") and l.count('"') % 2]
print("引号不配对行:", bad[:5] if bad else "无")

# 打印改后的片段供检查
inside = False
for i, l in enumerate(lines[88:130], start=89):
    print("%4d| %s" % (i, l))
