import json
import urllib.request

# 用 API 读文件内容（base64），比 raw CDN 稳
def read_file(path):
    url = "https://api.github.com/repos/Xyvern08371/ios-on-fuxi/contents/%s?ref=ci-logs" % path
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "dsh")
    req.add_header("Accept", "application/vnd.github+json")
    d = json.load(urllib.request.urlopen(req, timeout=30))
    import base64
    return base64.b64decode(d["content"]).decode("utf-8", "replace")


for f in ("step2-ArmCpu.log", "step2-NativeUfs.log", "step2-NativeAES.log"):
    try:
        t = read_file(f)
        print("=== %s (%d 字节) ===" % (f, len(t)))
        print(t)
        print()
    except Exception as e:
        print("%s: %s" % (f, e))
