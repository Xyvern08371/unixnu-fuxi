import io
import sys

P = r"E:\ios-on-fuxi\loader\Probe.c"
s = io.open(P, encoding="utf-8").read()

# 1) boot_args 结构与构造函数，插在 Halt 之前（不依赖绘图函数）
anchor = 'STATIC __attribute__((unused))\nVOID\nHalt ('
idx = s.find(anchor)
if idx < 0:
    print("找不到 Halt")
    sys.exit(1)

block = r'''/* ---------------- XNU 交接: boot_args ---------------- */

/*
 * 结构必须与目标 XNU 版本的 pexpert/arm64/boot.h 完全一致。
 * 这里按 xnu-8792.81.2 的定义（iOS 16 一代）。
 * 字段顺序、对齐、填充都由自然对齐产生，不能加 packed。
 */
typedef struct {
  UINT64  v_baseAddr;
  UINT64  v_display;
  UINT64  v_rowBytes;
  UINT64  v_width;
  UINT64  v_height;
  UINT64  v_depth;
} BOOT_VIDEO;

typedef struct {
  UINT16  Revision;
  UINT16  Version;
  UINT64  virtBase;
  UINT64  physBase;
  UINT64  memSize;
  UINT64  topOfKernelData;
  BOOT_VIDEO  Video;
  UINT32  machineType;
  VOID   *deviceTreeP;
  UINT32  deviceTreeLength;
  CHAR8   CommandLine[608];
  UINT64  bootFlags;
  UINT64  memSizeActual;
} BOOT_ARGS;

STATIC BOOT_ARGS  gBootArgs;

/** 填好 boot_args。参数都用物理地址（XNU 早期不认虚拟地址）。 */
STATIC __attribute__((unused)) VOID
BuildBootArgs (
  IN UINTN  Dtb,
  IN UINT32 DtbSize,
  IN UINTN  MemSize
  )
{
  UINTN  i;

  ZeroMem (&gBootArgs, sizeof (gBootArgs));

  gBootArgs.Revision        = 2;      /* kBootArgsRevision2 */
  gBootArgs.Version         = 2;      /* kBootArgsVersion2  */
  gBootArgs.virtBase        = 0;
  gBootArgs.physBase        = 0x80000000ULL;
  gBootArgs.memSize         = (UINT64) MemSize;
  gBootArgs.memSizeActual   = (UINT64) MemSize;
  gBootArgs.topOfKernelData = 0x80000000ULL + (UINT64) MemSize;

  gBootArgs.Video.v_baseAddr = (UINT64) (UINTN) mFb;
  gBootArgs.Video.v_display  = 0;
  gBootArgs.Video.v_rowBytes = (UINT64) mFbPitch * 4;
  gBootArgs.Video.v_width    = (UINT64) mFbW;
  gBootArgs.Video.v_height   = (UINT64) mFbH;
  gBootArgs.Video.v_depth    = 32;

  gBootArgs.machineType    = 0;
  gBootArgs.deviceTreeP    = (VOID *) Dtb;
  gBootArgs.deviceTreeLength = DtbSize;

  /* cmdline: 先用 -v (详细模式), 便于看到早期输出 */
  gBootArgs.CommandLine[0] = '-';
  gBootArgs.CommandLine[1] = 'v';
  gBootArgs.CommandLine[2] = 0;

  gBootArgs.bootFlags = 0;
  (VOID) i;
}

/** 跳到 XNU 入口: x0 = boot_args 指针, MMU 保持开启（先验证机制） */
STATIC __attribute__((unused)) VOID
JumpToBootArgs (
  IN UINTN  Entry,
  IN UINTN  BootArgs,
  IN UINTN  StackTop
  )
{
  __asm__ __volatile__ (
    "msr  daifset, #0xf\n"
    "mov  sp, %2\n"
    "mov  x0, %1\n"
    "br   %0\n"
    :
    : "r" (Entry), "r" (BootArgs), "r" (StackTop)
    : "memory"
    );
}

'''
s = s[:idx] + block + s[idx:]

# 2) 成功分支: 构造 boot_args 并传 &boot_args 给内核（自测模式）
old = '''      /* 退出成功: 跳到独立编译的内核 (M5) */
      if (mKernelStack != 0 && mKernelEntry != 0) {
        JumpToKernel (mKernelEntry, mFdtAddr,
                      (UINTN) mFb, (UINTN) mFbPitch, (UINTN) mFbH,
                      mKernelStack);
      }'''
new = '''      /* 退出成功: 构造 boot_args, 按 XNU 的约定传 x0=&boot_args (M6 自测) */
      if (mKernelStack != 0 && mKernelEntry != 0) {
        BuildBootArgs (mFdtAddr, mFdtSize, mMemSize);
        JumpToBootArgs (mKernelEntry, (UINTN) &gBootArgs, mKernelStack);
      }'''
if old not in s:
    print("找不到成功分支跳转")
    sys.exit(1)
s = s.replace(old, new)

# 3) 统计可用内存（供 boot_args 用）
s = s.replace("STATIC UINTN       mKernelEntry;",
              "STATIC UINTN       mKernelEntry;\nSTATIC UINTN       mMemSize;")

# 在内存图统计循环里累加 conventional 内存
old_loop = '''            if ((D->Attribute & EFI_MEMORY_RUNTIME) != 0) {
              Rt++;'''
new_loop = '''            if (D->Type == EfiConventionalMemory) {
              mMemSize += (UINTN) D->NumberOfPages * EFI_PAGE_SIZE;
            }
            if ((D->Attribute & EFI_MEMORY_RUNTIME) != 0) {
              Rt++;'''
if old_loop in s:
    s = s.replace(old_loop, new_loop, 1)

s = s.replace("[fuxi-probe v38]", "[fuxi-probe v39]").replace('L"v38 st=%r fb=%Lx', 'L"v39 st=%r fb=%Lx')

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("已加入 boot_args 构造与交接")
for ln, line in enumerate(s.split("\n"), 1):
    if any(k in line for k in ("BOOT_ARGS", "BuildBootArgs", "JumpToBootArgs", "mMemSize", "v39 st=")):
        print("  L%d: %s" % (ln, line.strip()[:80]))
