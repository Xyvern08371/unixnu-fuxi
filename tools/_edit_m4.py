import io
import sys

P = r"E:\ios-on-fuxi\loader\Probe.c"
s = io.open(P, encoding="utf-8").read()

payload = r'''
/* ---------------- M4: "内核"入口 ---------------- */

/**
  真实内核通过 x0 收到设备树指针。这里用同样的约定: x0 = 设备树物理地址。
  本函数只做一件事: 读设备树头部的 magic, 判断是不是合法 DTB, 并把结果画出来。
**/
STATIC __attribute__((unused)) VOID
PayloadEntry (
  IN UINT64  Dtb
  )
{
  CHAR8   Num[20];
  UINT32  Magic = 0;
  UINT32  yy;
  UINT8  *P = (UINT8 *) (UINTN) Dtb;

  if (P != NULL) {
    Magic = ((UINT32) P[0] << 24) | ((UINT32) P[1] << 16) |
            ((UINT32) P[2] << 8)  | (UINT32) P[3];
  }

  Fill (0xFF000000);

  yy = 120;
  DrawString (40, yy, "M4", 0xFFFFFFFF);
  yy += LINE_H;

  DrawString (40, yy, "DTB", 0xFFFFFFFF);
  Hex (Dtb, Num);
  DrawString (40 + 4 * 8 * SCALE, yy, Num, 0xFFFFFFFF);
  yy += LINE_H;

  DrawString (40, yy, "MAGIC", 0xFFFFFFFF);
  Hex ((UINT64) Magic, Num);
  DrawString (40 + 6 * 8 * SCALE, yy, Num, 0xFFFFFFFF);
  yy += LINE_H;

  DrawString (40, yy, Magic == 0xD00DFEEDUL ? "DT OK" : "DT BAD", 0xFFFFFFFF);

  /* 缓存回扫: 把像素挤到显存 */
  {
    volatile UINT32  *Pix = (volatile UINT32 *) mFb;
    UINTN             Total = mFbSize / 4;
    UINTN             k;
    for (k = 0; k < Total; k += 16) {
      UINT32  tmp = Pix[k];
      Pix[k] = tmp;
    }
  }

  for ( ; ; ) {
    __asm__ __volatile__ ("wfi");
  }
}

/** 关中断、换栈、x0=设备树, 跳到入口 */
STATIC __attribute__((unused)) VOID
JumpToPayload (
  IN UINTN  Entry,
  IN UINTN  Dtb,
  IN UINTN  StackTop
  )
{
  __asm__ __volatile__ (
    "msr  daifset, #0xf\n"
    "mov  sp, %2\n"
    "mov  x0, %1\n"
    "br   %0\n"
    :
    : "r" (Entry), "r" (Dtb), "r" (StackTop)
    : "memory"
    );
}

'''

anchor = 'STATIC __attribute__((unused))\nEFI_STATUS\nLeaveBootServices ('
idx = s.find(anchor)
if idx < 0:
    print("找不到 Halt 定义")
    sys.exit(1)
s = s[:idx] + payload + s[idx:]

old_branch = '''    } else {
      /* 退出成功: 控制台已经没了, 用自己画的点阵字体输出信息 (M3) */
'''
new_branch = '''    } else {
      /* 退出成功: 关中断 -> 换栈 -> x0=设备树 -> 跳到内核入口 (M4) */
      if (mKernelStack != 0) {
        JumpToPayload ((UINTN) PayloadEntry, mFdtAddr, mKernelStack);
      }
    }

    /* M3 的裸机自绘保留作对照, 正常流程不会走到 */
    if (0) {
'''
if old_branch not in s:
    print("未匹配成功分支")
    sys.exit(1)
s = s.replace(old_branch, new_branch)

s = s.replace("STATIC VOID       *mMapBuf;",
              "STATIC VOID       *mMapBuf;\nSTATIC UINTN       mKernelStack;")

old_alloc = "  mMapBuf     = AllocatePool (mMapBufSize);"
new_alloc = """  mMapBuf     = AllocatePool (mMapBufSize);

  /* 给内核准备 64KB 栈 */
  {
    EFI_PHYSICAL_ADDRESS  StackBase = 0;
    if (!EFI_ERROR (gBS->AllocatePages (AllocateAnyPages, EfiBootServicesData,
                                       16, &StackBase))) {
      mKernelStack = (UINTN) StackBase + 16 * EFI_PAGE_SIZE;
    }
  }"""
if old_alloc not in s:
    print("未匹配 mMapBuf 分配")
    sys.exit(1)
s = s.replace(old_alloc, new_alloc)

s = s.replace("[fuxi-probe v32]", "[fuxi-probe v33]").replace('L"v32 st=%r fb=%Lx', 'L"v33 st=%r fb=%Lx')

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("已写入 M4 版本")

for ln, line in enumerate(s.split("\n"), 1):
    if any(k in line for k in ("PayloadEntry", "JumpToPayload", "mKernelStack", "v33 st=")):
        print("  L%d: %s" % (ln, line.strip()[:90]))
