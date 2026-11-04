import io

# ---------- 1) XnuBoot.c：加 payload blob 符号与访问器 ----------
p = r"E:\ios-on-fuxi\loader\XnuBoot.c"
t = io.open(p, encoding="utf-8").read()

anchor = "VOID\nAsmXnuDcacheCleanRange ("
add = """/* payload 由 CI 生成的 xnu_payload.S 以 .incbin 方式嵌入 */
extern CONST UINT8  gXnuPayload[];
extern CONST UINT8  gXnuPayloadEnd[];

/** 返回内嵌 payload 的字节数（0 = 没嵌入） */
UINTN
XnuPayloadSize (
  VOID
  )
{
  return (UINTN)(gXnuPayloadEnd - gXnuPayload);
}

/** 返回内嵌 payload 的地址 */
CONST VOID *
XnuPayloadAddr (
  VOID
  )
{
  return (CONST VOID *)gXnuPayload;
}

"""
if "XnuPayloadSize" not in t:
    t = t.replace(anchor, add + anchor, 1)
    io.open(p, "w", encoding="utf-8", newline="\n").write(t)
    print("XnuBoot.c: 已加入 payload 符号")
else:
    print("XnuBoot.c: 已存在")

# ---------- 2) Probe.inf：加入 xnu_payload.S ----------
inf = r"E:\ios-on-fuxi\loader\Probe.inf"
s = io.open(inf, encoding="utf-8").read()
if "xnu_payload.S" not in s:
    s = s.replace("  xnu_jump.S\n", "  xnu_jump.S\n  xnu_payload.S\n")
    io.open(inf, "w", encoding="utf-8", newline="\n").write(s)
    print("Probe.inf: 已加入 xnu_payload.S")
else:
    print("Probe.inf: 已存在")

# ---------- 3) Probe.c：退出 Boot Services 后优先尝试 XNU ----------
pc = r"E:\ios-on-fuxi\loader\Probe.c"
c = io.open(pc, encoding="utf-8").read()

old = """      /* 退出成功: 构造 boot_args, 按 XNU 的约定传 x0=&boot_args (M6 自测) */
      if (mKernelStack != 0 && mKernelEntry != 0) {
        BuildBootArgs (mFdtAddr, mFdtSize, mMemSize);
        JumpToBootArgs (mKernelEntry, (UINTN) &gBootArgs, mKernelStack);
      }"""

new = """      /* 退出成功: 优先启动内嵌的 XNU payload；没有 payload 时退回 M5 自测内核 */
      if (XnuPayloadSize () > 0) {
        XnuBootRun (XnuPayloadAddr (), XnuPayloadSize (),
                    (UINTN) mFb, (UINTN) mFbPitch, mFbW, mFbH);
      }
      if (mKernelStack != 0 && mKernelEntry != 0) {
        BuildBootArgs (mFdtAddr, mFdtSize, mMemSize);
        JumpToBootArgs (mKernelEntry, (UINTN) &gBootArgs, mKernelStack);
      }"""

if old in c:
    c = c.replace(old, new)
    # 前向声明
    decl = """extern UINTN        XnuPayloadSize (VOID);
extern CONST VOID  *XnuPayloadAddr (VOID);
extern VOID         XnuBootRun (CONST VOID *, UINTN, UINTN, UINTN, UINT32, UINT32);

"""
    idx = c.index("STATIC") if "STATIC" in c else 0
    c = c[:idx] + decl + c[idx:]
    io.open(pc, "w", encoding="utf-8", newline="\n").write(c)
    print("Probe.c: 已加入 XNU 启动分支")
else:
    print("Probe.c: !! 未找到退出成功分支，需要人工处理")
