/** @file
  XnuMmu.c —— 自己建页表接管 TTBR0（简化版：4K 粒度 + 1GB 块）

  为什么用这个版本：
    第一版照搬 ios-sweet 的 16K 粒度页表，接管后立刻崩（UEFI 本身是 4K 粒度，
    换粒度等于换掉它全部的地址转换语义，风险太大）。

  现在：
    4K 粒度（和 UEFI 一致），T0SZ=25 → 39 位 VA
    level 1 用 1GB 块描述符，一张表 512 项覆盖 512GB
    前 16GB 全部映射为 Device-nGnRnE（够覆盖 DRAM、FV、帧缓冲、MMIO）
    不换粒度、只换表，UEFI 的其它假设尽量不动
**/

#include <Uefi.h>
#include <Library/BaseMemoryLib.h>

#define L1_ENTRIES   512
#define GB           0x40000000UL          /* 1GB */
#define MAP_GB       16                    /* 映射前 16GB */

#define ATTR_DEV     0
#define ATTR_WB      1
#define ATTR_NC      2
#define MAIR_VAL     0x44ff00UL

#define D_BLOCK      1UL
#define D_ATTR(i)    ((UINT64)(i) << 2)
#define D_AF         (1UL << 10)
#define D_PXN        (1UL << 53)
#define D_UXN        (1UL << 54)
#define DEV_FLAGS    (D_ATTR(ATTR_DEV) | D_AF | D_PXN | D_UXN)

/* T0SZ=25(39bit), IRGN0=WBWA, ORGN0=WBWA, SH0=inner, TG0=4K,
   EPD1=1(不用 TTBR1), IPS=2(40bit) */
#define TCR_VAL      (25UL | (1UL << 8) | (1UL << 10) | (3UL << 12) | \
                      (1UL << 23) | (2UL << 32))

#define RSR(r)   ({ UINT64 _v; __asm__ volatile ("mrs %0, " r : "=r"(_v)); _v; })
#define WSR(r, v) __asm__ volatile ("msr " r ", %0" : : "r"((UINT64)(v)))

STATIC UINT64  mL1[L1_ENTRIES] __attribute__((aligned(4096)));

/**
  安装我们自己的恒等映射（4K 粒度、1GB 块）。

  @retval 0 成功
**/
UINT32
XnuMmuInstall (
  IN UINTN  WbLo,
  IN UINTN  WbHi
  )
{
  UINTN   I;
  UINT64  Sctlr;

  (VOID)WbLo;
  (VOID)WbHi;

  /* L1: 前 16GB 全映射为 Device 块（恒等） */
  for (I = 0; I < L1_ENTRIES; I++) {
    mL1[I] = 0;
  }
  for (I = 0; I < MAP_GB; I++) {
    mL1[I] = ((UINT64)I * GB) | DEV_FLAGS | D_BLOCK;
  }

  /* 帧缓冲做成 non-cacheable（Device 也能写，但 NC 更快） */
  {
    UINTN  Fb = 0xB0000000UL;
    UINTN  Idx = Fb / GB;

    if (Idx < MAP_GB) {
      mL1[Idx] = ((UINT64)Idx * GB) | (D_ATTR(ATTR_NC) | D_AF | D_PXN | D_UXN) | D_BLOCK;
    }
  }

  __asm__ volatile ("dsb sy; ic iallu; dsb sy; isb" ::: "memory");

  WSR ("mair_el1", MAIR_VAL);
  WSR ("tcr_el1", TCR_VAL);
  WSR ("ttbr0_el1", (UINT64)(UINTN)mL1);
  __asm__ volatile ("isb; tlbi vmalle1; dsb nsh; isb" ::: "memory");

  Sctlr  = RSR ("sctlr_el1");
  Sctlr |= (1UL << 0) | (1UL << 2) | (1UL << 12);   /* M, C, I */
  WSR ("sctlr_el1", Sctlr);
  __asm__ volatile ("isb" ::: "memory");

  return 0;
}
