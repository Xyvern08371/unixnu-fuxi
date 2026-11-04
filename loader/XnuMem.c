/** @file
  XnuMem.c —— 为 XNU 挑一块 UEFI 认可的内存，并改写 ADT 的 dram-base/dram-size

  问题：ADT 里硬编码 dram-base = 0x100000000，但 UEFI 的页表没映射那块内存，
        拷贝内核段时触发 "Synchronous external abort"（实测）。

  做法：
    1. 退出 Boot Services 之前扫描 EFI 内存图，找一块足够大的 EfiConventionalMemory
    2. 把 ADT blob 里的 u64 0x100000000 / 0xfcc00000 原地替换成选中的值
       （ADT 是我们自己生成的，值已知，按字节模式替换是可靠的）
**/

#include <Uefi.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/MemoryAllocationLib.h>   /* AllocatePool / FreePool */

#define ADT_OLD_BASE  0x100000000ULL
#define ADT_OLD_SIZE  0xfcc00000ULL
#define NEED_BYTES    (48ULL * 1024 * 1024)   /* 内核 16MB + ADT + 余量 */

UINT64  mXnuPhysBase;
UINT64  mXnuPhysSize;

typedef VOID (*XNU_LOG_FN2)(CONST CHAR8 *Tag, UINT64 Value);

/**
  挑一块可用内存。

  @retval 0  找到
  @retval 1  没找到
**/
UINT32
XnuPickPhysRegion (
  IN  XNU_LOG_FN2  Log
  )
{
  EFI_STATUS            Status;
  EFI_PHYSICAL_ADDRESS  Pages = 0;
  UINTN                 Want;
  UINT64                End;

  mXnuPhysBase = 0;
  mXnuPhysSize = 0;

  /* 让 UEFI 直接分配：分配到的内存一定是映射好、可写的。
     内核 + ADT + boot_args 大约需要 32MB，这里按 48MB 申请。 */
  Want = (NEED_BYTES + 0x2000000ULL) / EFI_PAGE_SIZE;
  Status = gBS->AllocatePages (AllocateAnyPages, EfiLoaderData, Want, &Pages);
  if (EFI_ERROR (Status)) {
    if (Log != NULL) {
      Log ("ALLOC PAGES FAIL", (UINT64)Status);
    }
    return 1;
  }

  /*
   * XNU 的 start.s 用 32MB 块描述符建映射，physBase 必须 32MB 对齐，
   * 否则块边界和 virtBase 对不上，一开 MMU 就崩（实测症状：没有蓝带）。
   */
  mXnuPhysBase = ((UINT64)Pages + 0x1FFFFFFULL) & ~0x1FFFFFFULL;

  /* 告诉 XNU 的 dram 窗口：从这块开始，一直到 4GB（UEFI 大概只映射到这里） */
  End = 0x100000000ULL;
  if (End <= mXnuPhysBase + NEED_BYTES) {
    mXnuPhysSize = NEED_BYTES;
  } else {
    mXnuPhysSize = End - mXnuPhysBase;
  }
  mXnuPhysSize &= ~0x1FFFFFULL;

  if (Log != NULL) {
    Log ("PHYS PICKED", mXnuPhysBase);
    Log ("PHYS SIZE", mXnuPhysSize);
  }
  return 0;
}

/** 在 blob 里把所有 8 字节 LE 值 Old 换成 New */
STATIC
UINT32
PatchU64 (
  IN OUT UINT8   *Blob,
  IN     UINTN    Len,
  IN     UINT64   Old,
  IN     UINT64   New
  )
{
  UINTN   I;
  UINT32  Hits = 0;

  for (I = 0; I + 8 <= Len; I += 8) {
    UINT64  V;

    CopyMem (&V, Blob + I, 8);
    if (V == Old) {
      CopyMem (Blob + I, &New, 8);
      Hits++;
    }
  }
  return Hits;
}

/**
  把 ADT 里的 dram-base / dram-size 改成选中的内存。
  返回替换的处数（0 表示没找到，可能 ADT 不是我们生成的格式）。
**/
UINT32
XnuPatchAdt (
  IN OUT UINT8   *Adt,
  IN     UINTN    Len,
  IN     UINT64   Base,
  IN     UINT64   Size
  )
{
  UINT32  A;
  UINT32  B;

  A = PatchU64 (Adt, Len, ADT_OLD_BASE, Base);
  B = PatchU64 (Adt, Len, ADT_OLD_SIZE, Size);
  return A + B;
}
