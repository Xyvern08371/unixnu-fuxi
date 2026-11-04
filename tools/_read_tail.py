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
print("step1.log: %d 行" % len(lines))

print("\n=== 最后 50 行 ===")
for j in range(max(0, len(lines) - 50), len(lines)):
    print("%5d %s" % (j + 1, lines[j].rstrip()[:150]))
