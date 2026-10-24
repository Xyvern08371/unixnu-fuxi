import io
import sys

P = r"E:\ios-on-fuxi\loader\Probe.c"
s = io.open(P, encoding="utf-8").read()

# 1) 外部声明：内嵌内核
decl_anchor = "/* 由 tools/gen_dtb_blob.py 从 rom/device/fuxi_runtime.dtb 生成 */"
idx = s.find(decl_anchor)
if idx < 0:
    print("找不到内嵌设备树的声明处")
    sys.exit(1)
s = s[:idx] + ("/* 由 tools/gen_blob.py 从 payload/kernel.bin 生成 */\n"
               "extern CONST UINT8   gKernelData[];\n"
               "extern CONST UINT32  gKernelSize;\n\n") + s[idx:]

# 2) JumpToPayload 改成传 4 个参数（dtb/fb/pitch/height）
old_jump_start = s.find("STATIC __attribute__((unused)) VOID\nJumpToPayload (")
if old_jump_start < 0:
    print("找不到 JumpToPayload")
    sys.exit(1)
old_jump_end = s.find("\n}\n", old_jump_start) + 3
new_jump = '''STATIC __attribute__((unused)) VOID
JumpToKernel (
  IN UINTN  Entry,
  IN UINTN  Dtb,
  IN UINTN  Fb,
  IN UINTN  Pitch,
  IN UINTN  Height,
  IN UINTN  StackTop
  )
{
  __asm__ __volatile__ (
    "msr  daifset, #0xf\\n"      /* 关中断 */
    "mov  sp, %5\\n"             /* 换栈 */
    "mov  x0, %1\\n"             /* x0 = 设备树 */
    "mov  x1, %2\\n"             /* x1 = 帧缓冲 */
    "mov  x2, %3\\n"             /* x2 = 每行像素数 */
    "mov  x3, %4\\n"             /* x3 = 屏幕高度 */
    "br   %0\\n"                 /* 跳到内核入口 */
    :
    : "r" (Entry), "r" (Dtb), "r" (Fb), "r" (Pitch), "r" (Height), "r" (StackTop)
    : "memory"
    );
}
'''
s = s[:old_jump_start] + new_jump + s[old_jump_end:]

# 3) 成功分支：跳到内核而不是 PayloadEntry
old_call = '''      /* 退出成功: 关中断 -> 换栈 -> x0=设备树 -> 跳到内核入口 (M4) */
      if (mKernelStack != 0) {
        JumpToPayload ((UINTN) PayloadEntry, mFdtAddr, mKernelStack);
      }'''
new_call = '''      /* 退出成功: 跳到独立编译的内核 (M5) */
      if (mKernelStack != 0 && mKernelEntry != 0) {
        JumpToKernel (mKernelEntry, mFdtAddr,
                      (UINTN) mFb, (UINTN) mFbPitch, (UINTN) mFbH,
                      mKernelStack);
      }'''
if old_call not in s:
    print("找不到成功分支的跳转调用")
    sys.exit(1)
s = s.replace(old_call, new_call)

# 4) 全局变量
s = s.replace("STATIC UINTN       mKernelStack;",
              "STATIC UINTN       mKernelStack;\nSTATIC UINTN       mKernelEntry;")

# 5) 入口处把内核复制到页对齐缓冲区
alloc_anchor = '''  /* 给内核准备 64KB 栈 */'''
idx2 = s.find(alloc_anchor)
if idx2 < 0:
    print("找不到栈分配处")
    sys.exit(1)
load_code = '''  /* 把内嵌内核复制到页对齐的缓冲区（位置无关，可放任意地址） */
  if (gKernelSize > 0) {
    UINTN                 Pages = ((UINTN) gKernelSize + EFI_PAGE_SIZE - 1) / EFI_PAGE_SIZE;
    EFI_PHYSICAL_ADDRESS  Base  = 0;
    if (!EFI_ERROR (gBS->AllocatePages (AllocateAnyPages, EfiLoaderData,
                                       Pages, &Base))) {
      CopyMem ((VOID *) (UINTN) Base, (VOID *) gKernelData, (UINTN) gKernelSize);
      mKernelEntry = (UINTN) Base;
    }
  }

'''
s = s[:idx2] + load_code + s[idx2:]

s = s.replace("[fuxi-probe v37]", "[fuxi-probe v38]").replace('L"v37 st=%r fb=%Lx', 'L"v38 st=%r fb=%Lx')

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("已改为跳转到独立内核")

for ln, line in enumerate(s.split("\n"), 1):
    if any(k in line for k in ("gKernelData", "gKernelSize", "mKernelEntry", "JumpToKernel", "v38 st=")):
        print("  L%d: %s" % (ln, line.strip()[:88]))
