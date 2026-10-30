import io

p = r"E:\download\UniXNU\scripts\unixnu"
with open(p, "r", encoding="utf-8", errors="replace") as f:
    t = f.read()

lines = t.split("\n")
print("行数: %d" % len(lines))
print()
for i, l in enumerate(lines, 1):
    s = l.strip()
    if any(k in s for k in ("XNU_BOOTSTRAP", "BOOTSTRAP", "build-xnu-4k-baseline",
                            "def build_kernel", "def cmd_build", "def _kernel")):
        print("L%-5d %s" % (i, s[:130]))
