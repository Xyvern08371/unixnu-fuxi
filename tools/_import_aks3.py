"""导入 AppleKeyStore 补丁（修正 CRLF 和字符串替换）。"""

import io

SRC = r"E:\download\ios-sweet\xnu\patches\0038-sweet-applekeystore.patch"
OUT = r"E:\ios-on-fuxi\xnu\patches\0027-fuxi-applekeystore.patch"
P0016 = r"E:\ios-on-fuxi\xnu\patches\0016-fuxi-device-tree-platform-expert.patch"

# ---------- 0027 ----------
src = io.open(SRC, encoding="utf-8").read().replace("\r\n", "\n")
i = src.find("--- /dev/null")
lines = src[i:].split("\n")
hunk = next(k for k, l in enumerate(lines) if l.startswith("@@"))
body = lines[hunk + 1:]
while body and body[-1].strip() == "":
    body.pop()

out = []
for l in body:
    l = l.replace("SWEET AKS", "FUXI AKS")          # 日志字符串
    l = l.replace("SWEET_AKS", "FUXI_AKS")          # 宏
    l = l.replace("sweet_aks", "fuxi_aks")          # 函数
    l = l.replace("Sweet", "Fuxi").replace("sweet", "fuxi")
    l = l.replace("SWEET", "ARM64_BOARD_CONFIG_FUXI")   # 剩余门控
    out.append(l)

header = [
    "diff --git a/iokit/Kernel/arm/FuxiKeyStore.cpp b/iokit/Kernel/arm/FuxiKeyStore.cpp",
    "new file mode 100644",
    "--- /dev/null",
    "+++ b/iokit/Kernel/arm/FuxiKeyStore.cpp",
    "@@ -0,0 +1,%d @@" % len(out),
]
io.open(OUT, "w", encoding="utf-8", newline="\n").write("\n".join(header + out) + "\n")
print(f"0027 生成：{len(out)} 行")

# ---------- 0016 ----------
t16 = io.open(P0016, encoding="utf-8").read().replace("\r\n", "\n")

# a) files.arm64 加文件
if "FuxiKeyStore.cpp" not in t16:
    old = "+iokit/Kernel/arm/SweetPlatformExpert.cpp                         optional iokitcpp"
    assert old in t16, "files.arm64 锚点没找到"
    t16 = t16.replace(old, old + "\n+iokit/Kernel/arm/FuxiKeyStore.cpp                                optional iokitcpp", 1)
    print("files.arm64: 已加 FuxiKeyStore.cpp")
else:
    print("files.arm64: 已有")

# b) KernelConfigTables 加 AppleKeyStore 匹配
if "IOMatchCategory' = AppleKeyStore" not in t16:
    anchor = '''+#endif
+    "   {"
+    "     'IOClass'         = IOPanicPlatform;"'''
    insert = '''+#endif
+#if defined(ARM64_BOARD_CONFIG_FUXI)
+    "   {"
+    "     'IOClass'         = AppleKeyStore;"
+    "     'IOProviderClass' = IOResources;"
+    "     'IOMatchCategory' = AppleKeyStore;"
+    "   },"
+#endif
+    "   {"
+    "     'IOClass'         = IOPanicPlatform;"'''
    assert anchor in t16, "KernelConfigTables 锚点没找到"
    t16 = t16.replace(anchor, insert, 1)
    print("KernelConfigTables: 已加 AppleKeyStore 匹配")
else:
    print("KernelConfigTables: 已有")

io.open(P0016, "w", encoding="utf-8", newline="\n").write(t16)
