import io

p = r"E:\download\UniXNU\scripts\build-xnu-4k-baseline.sh"
lines = io.open(p, encoding="utf-8", errors="replace").read().split("\n")

print("=== L1-70 ===")
for i in range(0, 70):
    print("%4d %s" % (i + 1, lines[i].rstrip()[:118]))
