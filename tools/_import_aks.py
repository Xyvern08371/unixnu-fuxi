"""导入 ios-sweet 的 AppleKeyStore 补丁，适配 fuxi。

做三件事：
  1) 生成 0027-fuxi-applekeystore.patch（新建 iokit/Kernel/arm/FuxiKeyStore.cpp）
     - Sweet -> Fuxi，SWEET -> ARM64_BOARD_CONFIG_FUXI
  2) 在 0016 的 files.arm64 hunk 里加上这个文件
  3) 在 0016 的 KernelConfigTables hunk 里加上 AppleKeyStore 匹配项
"""

import io
import re

SRC = r"E:\download\ios-sweet\xnu\patches\0038-sweet-applekeystore.patch"
OUT = r"E:\ios-on-fuxi\xnu\patches\0027-fuxi-applekeystore.patch"
P0016 = r"E:\ios-on-fuxi\xnu\patches\0016-fuxi-device-tree-platform-expert.patch"

src = io.open(SRC, encoding="utf-8").read()

# ---- 1) 取出新文件那段 ----
i = src.find("--- /dev/null")
assert i >= 0, "找不到新文件段"
section = src[i:]

# 拆出 @@ 行和正文
lines = section.split("\n")
hunk_idx = next(k for k, l in enumerate(lines) if l.startswith("@@"))
body = lines[hunk_idx + 1:]
# 去掉尾部空行
while body and body[-1].strip() == "":
    body.pop()

assert all(l.startswith("+") or l == "" for l in body), "新文件段不是纯 + 行"

# 改名：Sweet -> Fuxi（只在正文里）
renamed = []
for l in body:
    l = l.replace("SWEET", "ARM64_BOARD_CONFIG_FUXI")
    l = l.replace("Sweet", "Fuxi")
    l = l.replace("sweet", "fuxi")
    renamed.append(l)

# ---- 2) 生成 0027 ----
header = [
    "diff --git a/iokit/Kernel/arm/FuxiKeyStore.cpp b/iokit/Kernel/arm/FuxiKeyStore.cpp",
    "new file mode 100644",
    "--- /dev/null",
    "+++ b/iokit/Kernel/arm/FuxiKeyStore.cpp",
    "@@ -0,0 +1,%d @@" % len(renamed),
]
io.open(OUT, "w", encoding="utf-8", newline="\n").write("\n".join(header + renamed) + "\n")
print(f"生成 {OUT.split(chr(92))[-1]}：{len(renamed)} 行")

# ---- 3) 扩展 0016 ----
t16 = io.open(P0016, encoding="utf-8").read()

# 3a) files.arm64
old = "+iokit/Kernel/arm/SweetPlatformExpert.cpp                         optional iokitcpp"
assert old in t16
new = old + "\n+iokit/Kernel/arm/FuxiKeyStore.cpp                                optional iokitcpp"
t16 = t16.replace(old, new, 1)

# 3b) KernelConfigTables：在 FUXI 平台专家条目后加 AppleKeyStore
old2 = '''+#endif
+    "   {"
+    "     'IOClass'         = IOPanicPlatform;"'''
assert old2 in t16, "KernelConfigTables 锚点没找到"
new2 = '''+#endif
+#if defined(ARM64_BOARD_CONFIG_FUXI)
+    "   {"
+    "     'IOClass'         = AppleKeyStore;"
+    "     'IOProviderClass' = IOResources;"
+    "     'IOMatchCategory' = AppleKeyStore;"
+    "   },"
+#endif
+    "   {"
+    "     'IOClass'         = IOPanicPlatform;"'''
t16 = t16.replace(old2, new2, 1)

io.open(P0016, "w", encoding="utf-8", newline="\n").write(t16)
print("0016 已加入 FuxiKeyStore.cpp 和 AppleKeyStore 匹配项")
