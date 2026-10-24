import io

p = r"E:\download\UniXNU\scripts\build-xnu-4k-baseline.sh"
lines = io.open(p, encoding="utf-8", errors="replace").read().split("\n")
for i, l in enumerate(lines, 1):
    s = l.strip()
    if "BOOTSTRAP" in s and "=" in s and not s.startswith("#"):
        print("L%-4d %s" % (i, s[:130]))
