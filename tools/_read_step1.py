import base64
import json
import urllib.request


def read_file(path):
    url = "https://api.github.com/repos/Xyvern08371/ios-on-fuxi/contents/%s?ref=ci-logs" % path
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "dsh")
    req.add_header("Accept", "application/vnd.github+json")
    d = json.load(urllib.request.urlopen(req, timeout=60))
    return base64.b64decode(d["content"]).decode("utf-8", "replace")


t = read_file("step1.log")
print("step1.log: %d 字节" % len(t))

# 找 cpo.json 的实际路径
import re

print("\n=== 提到 cpo.json 的行 ===")
hits = [l for l in t.split("\n") if "cpo.json" in l]
for l in hits[:30]:
    print("  " + l.strip()[:150])
print("  ... 共 %d 行" % len(hits))

print("\n=== 提到 ios-obj 的行 ===")
hits2 = [l for l in t.split("\n") if "ios-obj" in l]
for l in hits2[:25]:
    print("  " + l.strip()[:150])
print("  ... 共 %d 行" % len(hits2))

print("\n=== 提到 -MJ 的行 ===")
hits3 = [l for l in t.split("\n") if "-MJ" in l]
for l in hits3[:10]:
    print("  " + l.strip()[:180])
print("  ... 共 %d 行" % len(hits3))

print("\n=== 最后 30 行 ===")
for l in t.split("\n")[-30:]:
    print("  " + l.strip()[:150])
