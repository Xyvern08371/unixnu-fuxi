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

# ci-logs 分支上现在应该是第 13 次的日志
t = read_file("step1.log")
print("step1.log: %d 字节" % len(t))

lines = t.split("\n")

# 找报错和最后的 trace
print("\n=== 含 error / Error / exit 1 / cannot 的行（最后 20 条）===")
hits = [(i + 1, l) for i, l in enumerate(lines)
        if any(k in l for k in ("rror", "exit 1", "annot ", "No such", "not found"))]
for ln, l in hits[-20:]:
    print("  L%-6d %s" % (ln, l.strip()[:150]))

print("\n=== 最后 40 行 ===")
for l in lines[-40:]:
    print("  " + l.rstrip()[:150])
