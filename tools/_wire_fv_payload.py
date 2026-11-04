"""把 FV 读取接进加载器，并在 FDF 里插入 RAW section。"""

import io

# ---------- 1) Probe.c：优先用 FV ----------
Q = r"E:\ios-on-fuxi\loader\Probe.c"
c = io.open(Q, encoding="utf-8").read()

c = c.replace(
    "extern EFI_STATUS   XnuLoadFromUfs (VOID **Buf, UINTN *Size,",
    "extern EFI_STATUS   XnuLoadFromFv (VOID **Buf, UINTN *Size,\n"
    "                                   VOID (*Log)(CONST CHAR8 *, UINT64));\n"
    "extern EFI_STATUS   XnuLoadFromUfs (VOID **Buf, UINTN *Size,",
    1,
)

old = """      XnuLoadFromBlock (&mXnuBuf, &mXnuBufSize, XnuScreenLog);
      if (mXnuBufSize == 0) {
        XnuScreenLog ("BLK EMPTY, TRY UFS", 0);
        XnuLoadFromUfs (&mXnuBuf, &mXnuBufSize, XnuScreenLog);
      }"""
new = """      XnuLoadFromFv (&mXnuBuf, &mXnuBufSize, XnuScreenLog);
      if (mXnuBufSize == 0) {
        XnuScreenLog ("FV EMPTY, TRY BLK", 0);
        XnuLoadFromBlock (&mXnuBuf, &mXnuBufSize, XnuScreenLog);
      }"""
assert old in c, "Probe 加载段没找到"
c = c.replace(old, new, 1)
io.open(Q, "w", encoding="utf-8", newline="\n").write(c)
print("Probe.c 已改为优先 FV")

# ---------- 2) INF：加 XnuFv.c 与 FV 协议 ----------
inf = r"E:\ios-on-fuxi\loader\Probe.inf"
s = io.open(inf, encoding="utf-8").read()
if "XnuFv.c" not in s:
    s = s.replace("  XnuLoad.c\n", "  XnuLoad.c\n  XnuFv.c\n")
if "gEfiFirmwareVolume2ProtocolGuid" not in s:
    s = s.replace("[Protocols]\n", "[Protocols]\n  gEfiFirmwareVolume2ProtocolGuid\n")
io.open(inf, "w", encoding="utf-8", newline="\n").write(s)
print(s[s.index("[Sources]"):s.index("[Packages]")])

# ---------- 3) CI：注入 FDF RAW section + 复制 XnuFv.c ----------
W = r"E:\ios-on-fuxi\.github\workflows\build-fuxi-uefi.yml"
w = io.open(W, encoding="utf-8").read()

w = w.replace(
    "             loader/XnuBoot.c loader/XnuLoad.c loader/XnuUfs.c loader/xnu_jump.S loader/xnu_payload.S \"$probe\"/",
    "             loader/XnuBoot.c loader/XnuLoad.c loader/XnuFv.c loader/XnuUfs.c loader/xnu_jump.S loader/xnu_payload.S \"$probe\"/",
)

# FDF 插入 RAW file（放在探针 INF 之后）
anchor = "          sed -i '/INF MdeModulePkg\\/Universal\\/BdsDxe\\/BdsDxe.inf/a\\  INF Platform/Xiaomi/sm8550/probe/Probe.inf' \\\n            edk2-msm/Platform/Qualcomm/sm8550/sm8550.fdf"
if anchor not in w:
    raise SystemExit("找不到 FDF 插入锚点")

extra = anchor + r'''

          echo "=== 把 XNU payload 作为 RAW section 塞进 FV ==="
          if [ -f rom/xnu/payload-blob.img ]; then
            cp rom/xnu/payload-blob.img edk2-msm/Platform/Xiaomi/sm8550/probe/xnu_payload.bin
            ls -l edk2-msm/Platform/Xiaomi/sm8550/probe/xnu_payload.bin
            if ! grep -q "XNU PAYLOAD" edk2-msm/Platform/Qualcomm/sm8550/sm8550.fdf; then
              sed -i "/INF Platform\/Xiaomi\/sm8550\/probe\/Probe.inf/a\\
  FILE FREEFORM = 9f3c7a21-5b4e-4c8d-9a11-7e2b6308d451 {   # XNU PAYLOAD\n    SECTION RAW = Platform/Xiaomi/sm8550/probe/xnu_payload.bin\n  }" \
                edk2-msm/Platform/Qualcomm/sm8550/sm8550.fdf
              echo "已插入 FV RAW section"
            fi
            grep -n -A3 "XNU PAYLOAD" edk2-msm/Platform/Qualcomm/sm8550/sm8550.fdf || true
          else
            echo "没有 payload-blob.img，跳过 FV 注入"
          fi'''
w = w.replace(anchor, extra, 1)

io.open(W, "w", encoding="utf-8", newline="\n").write(w)
print("CI 已加 FDF RAW 注入")

lines = w.split("\n")
bad = [i for i, l in enumerate(lines, 1) if not l.strip().startswith("#") and l.count('"') % 2]
print("引号不配对:", bad[:5] if bad else "无")
