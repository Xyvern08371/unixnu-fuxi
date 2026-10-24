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
print("step1.log: %d 字节, %d 行" % (len(t), len(lines)))

print("\n=== 有没有 clang 编译行 ===")
clang_lines = [l for l in lines if "clang" in l and "-c" in l]
print("  %d 行含 clang -c" % len(clang_lines))
for l in clang_lines[:5]:
    print("    " + l.strip()[:180])

print("\n=== 有没有 make 调用 ===")
make_lines = [l for l in lines if l.strip().startswith("+ make") or "make " in l and "xnu" in l.lower()]
for l in make_lines[:10]:
    print("    " + l.strip()[:180])

print("\n=== 有没有 'Building' / 'KCC' / 'CC ' 之类 ===")
b = [l for l in lines if any(k in l for k in ("Building", "KCC", "CC ", "clang -"))]
print("  %d 行" % len(b))
for l in b[:8]:
    print("    " + l.strip()[:180])

print("\n=== build/ 目录相关 ===")
bb = [l for l in lines if "build/xnu" in l and ("mkdir" in l or "ios-obj" in l)]
print("  %d 行" % len(bb))
for l in bb[:10]:
    print("    " + l.strip()[:180])
