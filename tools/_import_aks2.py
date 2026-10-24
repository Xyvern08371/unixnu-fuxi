"""修正导入：宏名保持干净（SWEET_AKS -> FUXI_AKS），并把 AppleKeyStore 条目插进 0016。"""

import io

SRC = r"E:\download\ios-sweet\xnu\patches\0038-sweet-applekeystore.patch"
OUT = r"E:\ios-on-fuxi\xnu\patches\0027-fuxi-applekeystore.patch"
P0016 = r"E:\ios-on-fuxi\xnu\patches\0016-fuxi-device-tree-platform-expert.patch"

src = io.open(SRC, encoding="utf-8").read()
i = src.find("--- /dev/null")
section = src[i:]
lines = section.split("\n")
hunk_idx = next(k for k, l in enumerate(lines) if l.startswith("@@"))
body = lines[hunk_idx + 1:]
while body and body[-1].strip() == "":
    body.pop()

renamed = []
for l in body:
    # 先处理带下划线前缀的宏，避免变成 ARM64_BOARD_CONFIG_FUXI_AKS_*
    l = l.replace("SWEET_AKS", "FUXI_AKS")
    l = l.replace("sweet_aks", "fuxi_aks")
    l = l.replace("Sweet", "Fuxi").replace("sweet", "fuxi")
    l = l.replace("SWEET", "ARM64_BOARD_CONFIG_FUXI")
    renamed.append(l)

header = [
    "diff --git a/iokit/Kernel/arm/FuxiKeyStore.cpp b/iokit/Kernel/arm/FuxiKeyStore.cpp",
    "new file mode 100644",
    "--- /dev/null",
    "+++ b/iokit/Kernel/arm/FuxiKeyStore.cpp",
    "@@ -0,0 +1,%d @@" % len(renamed),
]
io.open(OUT, "w", encoding="utf-8", newline="\n").write("\n".join(header + renamed) + "\n")
print(f"0027 重新生成：{len(renamed)} 行")

# --- 0016：加 AppleKeyStore 匹配（用精确锚点）---
t16 = io.open(P0016, encoding="utf-8").read()

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

if "IOMatchCategory' = AppleKeyStore" in t16:
    print("0016 已有 AppleKeyStore 条目")
else:
    assert anchor in t16, "锚点仍未找到"
    t16 = t16.replace(anchor, insert, 1)
    io.open(P0016, "w", encoding="utf-8", newline="\n").write(t16)
    print("0016 已插入 AppleKeyStore 匹配项")

# --- files.arm64 条目 ---
t16 = io.open(P0016, encoding="utf-8").read()
if "FuxiKeyStore.cpp" not in t16:
    old = "+iokit/Kernel/arm/SweetPlatformExpert.cpp                         optional iokitcpp"
    assert old in t16
    t16 = t16.replace(old, old + "\n+iokit/Kernel/arm/FuxiKeyStore.cpp                                optional iokitcpp", 1)
    io.open(P0016, "w", encoding="utf-8", newline="\n").write(t16)
    print("0016 已加入 FuxiKeyStore.cpp 到 files.arm64")
else:
    print("files.arm64 已有 FuxiKeyStore.cpp")
