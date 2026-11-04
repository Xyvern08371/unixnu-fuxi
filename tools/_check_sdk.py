import io

p = r"E:\download\UniXNU\scripts\build-xnu-4k-baseline.sh"
lines = io.open(p, encoding="utf-8", errors="replace").read().split("\n")

print("=== SDKROOT / Xcode / iphoneos 相关 ===")
for i, l in enumerate(lines, 1):
    s = l.strip()
    if any(k in s for k in ("SDKROOT", "xcodebuild", "xcrun", "iphoneos", "KERNEL_SDKROOT", "SDK")):
        if not s.startswith("#"):
            print("L%-5d %s" % (i, s[:130]))
