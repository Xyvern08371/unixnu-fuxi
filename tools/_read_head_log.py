import base64
import json
import urllib.request


def read_file(path, ref="ci-logs"):
    url = "https://api.github.com/repos/Xyvern08371/ios-on-fuxi/contents/%s?ref=%s" % (path, ref)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "dsh")
    req.add_header("Accept", "application/vnd.github+json")
    d = json.load(urllib.request.urlopen(req, timeout=60))
    return base64.b64decode(d["content"]).decode("utf-8", "replace")


t = read_file("step1.log")
lines = t.split("\n")
print("总行数: %d" % len(lines))

print("\n=== 前 40 行 ===")
for i in range(0, min(40, len(lines))):
    print("%4d %s" % (i + 1, lines[i].rstrip()[:140]))

print("\n=== 搜 BOOTSTRAP 出现处 ===")
for i, l in enumerate(lines):
    if "BOOTSTRAP" in l:
        print("%4d %s" % (i + 1, l.strip()[:140]))

print("\n=== 搜 prepare-xnu-source 之后紧跟的 30 行 ===")
for i, l in enumerate(lines):
    if "prepare-xnu-source" in l:
        for j in range(i, min(len(lines), i + 30)):
            print("%4d %s" % (j + 1, lines[j].rstrip()[:140]))
        break
