import base64
import json
import urllib.request

# 从 ci-logs 分支读不到脚本，但可以从仓库读
url = "https://api.github.com/repos/Xyvern08371/ios-on-fuxi/contents/vendor/UniXNU-full.tar.gz"
req = urllib.request.Request(url)
req.add_header("User-Agent", "dsh")
req.add_header("Accept", "application/vnd.github+json")
try:
    d = json.load(urllib.request.urlopen(req, timeout=30))
    print("vendor tarball:", d.get("size"), "字节")
except Exception as e:
    print("err:", e)

# 读 workflow 全文的 step1 部分已经看过了。
# 关键：检查 PS4 为什么没生效 —— 看日志第一行
url2 = "https://api.github.com/repos/Xyvern08371/ios-on-fuxi/contents/step1.log?ref=ci-logs"
req2 = urllib.request.Request(url2)
req2.add_header("User-Agent", "dsh")
req2.add_header("Accept", "application/vnd.github+json")
d2 = json.load(urllib.request.urlopen(req2, timeout=60))
t = base64.b64decode(d2["content"]).decode("utf-8", "replace")
lines = t.split("\n")
print("\n日志前 3 行:")
for l in lines[:3]:
    print("  " + repr(l))
print("\nL306-315:")
for i in range(305, min(len(lines), 315)):
    print("%4d %s" % (i + 1, lines[i].rstrip()[:140]))
