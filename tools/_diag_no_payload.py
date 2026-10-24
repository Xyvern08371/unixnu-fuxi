import io

W = r"E:\ios-on-fuxi\.github\workflows\build-fuxi-uefi.yml"
t = io.open(W, encoding="utf-8").read()

# 1) payload 步骤开头加一个开关（PAYLOAD_ENABLED: off 时直接跳过，保持占位 .S）
old = '          mkdir -p rom/xnu\n'
new = ('          mkdir -p rom/xnu\n\n'
       '          # 诊断开关：设为 off 时完全不嵌入 XNU，用来区分"模块太大导致的崩溃"\n'
       '          if [ "${PAYLOAD_ENABLED:-on}" = "off" ]; then\n'
       '            echo "PAYLOAD_ENABLED=off，跳过 XNU 嵌入（保持占位）"\n'
       '            cp xnu-payload.log ../xnu-payload.log 2>/dev/null || true\n'
       '            exit 0\n'
       '          fi\n')
assert old in t
t = t.replace(old, new, 1)

# 2) env 里加开关（先设为 off 做实验）
if "PAYLOAD_ENABLED" not in t.split("jobs:")[0]:
    t = t.replace("permissions:\n", "env:\n  PAYLOAD_ENABLED: \"off\"   # 诊断: off=不嵌 XNU\n\npermissions:\n", 1)

# 3) 诊断步骤里导出 Probe.efi 与反汇编（ubuntu runner 有 aarch64 objdump）
anchor = None
for i, l in enumerate(t.split("\n")):
    if l.strip().startswith("- name:") and "诊断" in l:
        anchor = i
        break
lines = t.split("\n")
if anchor is not None:
    end = anchor + 1
    while end < len(lines) and not lines[end].strip().startswith("- "):
        end += 1
    extra = [
        "          echo '=== 导出 Probe.efi 并反汇编 ==='",
        "          PROBE=$(find edk2-msm/workspace -name 'Probe.efi' -type f | head -1)",
        "          echo \"Probe.efi: [$PROBE]\"",
        "          if [ -n \"$PROBE\" ]; then",
        "            cp \"$PROBE\" . 2>/dev/null || true",
        "            ls -l Probe.efi 2>/dev/null || true",
        "            (aarch64-linux-gnu-objdump -d \"$PROBE\" | head -4000 > probe.dis) 2>/dev/null || true",
        "            ls -l probe.dis 2>/dev/null || true",
        "          fi",
        "",
    ]
    lines[anchor + 1:anchor + 1] = []  # no-op guard
    lines[end:end] = extra
    t = "\n".join(lines)

io.open(W, "w", encoding="utf-8", newline="\n").write(t)

# 4) 产物里加 Probe.efi / probe.dis
t = io.open(W, encoding="utf-8").read()
if "            probe.dis" not in t:
    t = t.replace("            build.log\n", "            build.log\n            probe.dis\n            Probe.efi\n")
    io.open(W, "w", encoding="utf-8", newline="\n").write(t)

lines = io.open(W, encoding="utf-8").read().split("\n")
bad = [i for i, l in enumerate(lines, 1) if not l.strip().startswith("#") and l.count('"') % 2]
print("引号不配对:", bad[:5] if bad else "无")
print("PAYLOAD_ENABLED 出现:", sum("PAYLOAD_ENABLED" in l for l in lines))
print("probe.dis 出现:", sum("probe.dis" in l for l in lines))
