/** @file
  XnuUfs.c —— 直接读 UFS（绕过 UEFI 的驱动栈）

  为什么需要它：这版 fuxi 固件没有 UFS DXE 驱动，EFI_BLOCK_IO 一个设备都
  枚举不到，所以内核 payload 读不出来。

  实现来源：dipa-studio/ios-sweet 的 shim/ufs.c（骁龙 732G 上跑通），
  寄存器布局按 JEDEC UFSHCI (JESD223)，只做只读操作。

  与他们的版本差异：
    · UEFI 下内存是 cacheable 的，DMA 前后要做缓存维护（他们的裸机版不需要）
    · 去掉了 con_* 打印，改成返回错误码
**/

#include <Uefi.h>
#include <Library/BaseLib.h>              /* AsciiStrLen / AsciiStrCmp */
#include <Library/BaseMemoryLib.h>        /* ZeroMem */
#include <Library/MemoryAllocationLib.h>  /* AllocatePool / FreePool */

#define UFS_BASE     0x01d84000UL

#define REG_CAP      0x00
#define REG_VER      0x08
#define REG_IS       0x20
#define REG_HCS      0x30
#define REG_HCE      0x34
#define REG_UTRLBA   0x50
#define REG_UTRLBAU  0x54
#define REG_UTRLDBR  0x58
#define REG_UTRLCLR  0x5c
#define REG_UTRLRSR  0x60

#define HCS_DP       (1u << 0)
#define HCS_UTRLRDY  (1u << 1)
#define HCS_UCRDY    (1u << 3)

#define UFS_BLOCK    4096u

typedef struct {
  UINT32  dw0;
  UINT32  dw1;
  UINT32  dw2;
  UINT32  dw3;
  UINT32  ucdba;
  UINT32  ucdbau;
  UINT32  resp;
  UINT32  prdt;
} UTRD;

typedef struct {
  UINT8   cmd[512];
  UINT8   resp[512];
  struct {
    UINT32  addr_lo;
    UINT32  addr_hi;
    UINT32  rsvd;
    UINT32  dbc;
  } Prdt[1];
} UCD;

STATIC UTRD  mUtrl[32] __attribute__((aligned(1024)));
STATIC UCD   mUcd __attribute__((aligned(128)));
STATIC UINT8 mUfsData[2 * UFS_BLOCK] __attribute__((aligned(4096)));

extern VOID AsmXnuDcacheCleanRange (UINTN Start, UINTN End);

STATIC UINT32
UfsRd (
  UINT32  Off
  )
{
  return *(volatile UINT32 *)(UFS_BASE + Off);
}

STATIC VOID
UfsWr (
  UINT32  Off,
  UINT32  Val
  )
{
  *(volatile UINT32 *)(UFS_BASE + Off) = Val;
}

STATIC UINT64
UfsTicks (
  VOID
  )
{
  UINT64  T;

  __asm__ volatile ("isb; mrs %0, cntvct_el0" : "=r" (T));
  return T;
}

STATIC VOID
ZeroBytes (
  VOID    *P,
  UINTN   N
  )
{
  volatile UINT8  *B = (volatile UINT8 *)P;
  UINTN           I;

  for (I = 0; I < N; I++) {
    B[I] = 0;
  }
}

/**
  发一条 SCSI 命令（slot 0）。

  @retval 0  成功
  @retval 1  超时
  @retval 2  OCS 非零
  @retval 3  响应不是 RESPONSE UPIU
  @retval 4  SCSI 状态非零
**/
STATIC UINT32
UfsScsi (
  UINT8   Lun,
  CONST UINT8  *Cdb,
  UINTN   CdbLen,
  VOID    *Buf,
  UINT32  Len
  )
{
  STATIC UINT8  Tag;
  UINTN         UcdPa;
  UINTN         BufPa;
  UINT64        Start;
  UINTN         I;
  UINT32        Ocs;

  ZeroBytes (&mUtrl[0], sizeof (mUtrl[0]));
  ZeroBytes (&mUcd, sizeof (mUcd));

  mUcd.cmd[0] = 0x01;
  mUcd.cmd[1] = (Len != 0) ? 0x40 : 0x00;
  mUcd.cmd[2] = Lun;
  mUcd.cmd[3] = ++Tag;
  mUcd.cmd[12] = (UINT8)(Len >> 24);
  mUcd.cmd[13] = (UINT8)(Len >> 16);
  mUcd.cmd[14] = (UINT8)(Len >> 8);
  mUcd.cmd[15] = (UINT8)Len;
  for (I = 0; I < CdbLen; I++) {
    mUcd.cmd[16 + I] = Cdb[I];
  }

  UcdPa = (UINTN)&mUcd;
  mUtrl[0].dw0     = (1u << 28) | ((Len != 0) ? (2u << 25) : 0u) | (1u << 24);
  mUtrl[0].dw2     = 0x0f;
  mUtrl[0].ucdba   = (UINT32)UcdPa;
  mUtrl[0].ucdbau  = (UINT32)(UcdPa >> 32);
  mUtrl[0].resp    = (512u / 4) << 16 | (512u / 4);
  if (Len != 0) {
    BufPa            = (UINTN)Buf;
    mUcd.Prdt[0].addr_lo = (UINT32)BufPa;
    mUcd.Prdt[0].addr_hi = (UINT32)(BufPa >> 32);
    mUcd.Prdt[0].dbc     = Len - 1;
    mUtrl[0].prdt    = (1024u / 4) << 16 | 1;
  }

  /* 描述符要给设备看：先刷出缓存 */
  AsmXnuDcacheCleanRange ((UINTN)&mUtrl[0], (UINTN)&mUtrl[0] + sizeof (mUtrl[0]));
  AsmXnuDcacheCleanRange ((UINTN)&mUcd, (UINTN)&mUcd + sizeof (mUcd));

  __asm__ volatile ("dsb sy" ::: "memory");

  UfsWr (REG_UTRLDBR, 1);
  Start = UfsTicks ();
  while ((UfsRd (REG_UTRLDBR) & 1) != 0) {
    if (UfsTicks () - Start > 19200000ULL) {
      UfsWr (REG_UTRLCLR, ~1u);
      return 1;
    }
  }
  __asm__ volatile ("dsb sy" ::: "memory");

  /* 设备写进来的数据要作废掉缓存，才能读到新内容 */
  if (Len != 0) {
    AsmXnuDcacheCleanRange ((UINTN)Buf, (UINTN)Buf + Len);
  }

  Ocs = mUtrl[0].dw2 & 0xff;
  if (Ocs != 0) {
    return 2;
  }
  if (mUcd.resp[0] != 0x21) {
    return 3;
  }
  if (mUcd.resp[7] != 0) {
    return 4;
  }
  return 0;
}

/**
  读若干 4K 块（LUN 0）。

  @retval 0  成功
**/
UINT32
UfsReadBlocks (
  UINT64  Lba,
  UINT32  Count,
  VOID    *Buf
  )
{
  UINT8  Cdb[10];

  Cdb[0] = 0x28;                                  /* READ(10) */
  Cdb[1] = 0;
  Cdb[2] = (UINT8)(Lba >> 24);
  Cdb[3] = (UINT8)(Lba >> 16);
  Cdb[4] = (UINT8)(Lba >> 8);
  Cdb[5] = (UINT8)Lba;
  Cdb[6] = 0;
  Cdb[7] = (UINT8)(Count >> 8);
  Cdb[8] = (UINT8)Count;
  Cdb[9] = 0;
  return UfsScsi (0, Cdb, sizeof (Cdb), Buf, Count * UFS_BLOCK);
}

/** 控制器是否就绪（ABL 应该已经把它跑起来了） */
UINT32
UfsReady (
  VOID
  )
{
  UINT32  Hcs;

  Hcs = UfsRd (REG_HCS);
  if ((Hcs & HCS_UTRLRDY) != 0) {
    return 0;
  }

  /* 没就绪：试着打开 */
  UfsWr (REG_HCE, 1);
  {
    UINT64  Start = UfsTicks ();

    while ((UfsRd (REG_HCS) & HCS_UTRLRDY) == 0) {
      if (UfsTicks () - Start > 19200000ULL) {
        return 1;
      }
    }
  }
  return 0;
}

/** 读第 lba 块到内部缓冲，供 GPT 解析用 */
STATIC UINT8 *
UfsOneBlock (
  UINT64  Lba
  )
{
  if (UfsReadBlocks (Lba, 1, mUfsData) != 0) {
    return NULL;
  }
  return mUfsData;
}

STATIC UINT64
Le64 (
  CONST UINT8  *P
  )
{
  UINT64  V = 0;
  INTN    I;

  for (I = 7; I >= 0; I--) {
    V = (V << 8) | P[I];
  }
  return V;
}

STATIC UINT32
Le32 (
  CONST UINT8  *P
  )
{
  return (UINT32)P[0] | ((UINT32)P[1] << 8) | ((UINT32)P[2] << 16) | ((UINT32)P[3] << 24);
}

/**
  在 GPT 里按名字找分区。

  @param[in]  Name      分区名（UTF-8，最多 16 字节）
  @param[out] FirstLba  起始 LBA
  @param[out] LastLba   结束 LBA（含）

  @retval 0 找到
**/
UINT32
UfsFindPartition (
  CONST CHAR8  *Name,
  UINT64       *FirstLba,
  UINT64       *LastLba
  )
{
  UINT8   *Hdr;
  UINT64  EntLba;
  UINT32  EntCount;
  UINT32  EntSize;
  UINT32  Blocks;
  UINT8   *Ents;
  UINT32  I;
  UINT32  J;

  if (UfsReady () != 0) {
    return 10;
  }

  Hdr = UfsOneBlock (1);                      /* GPT 头在 LBA 1 */
  if (Hdr == NULL) {
    return 11;
  }
  if (Hdr[0] != 'E' || Hdr[1] != 'F' || Hdr[2] != 'I' || Hdr[3] != ' ' || Hdr[4] != 'P' || Hdr[5] != 'A' || Hdr[6] != 'R' || Hdr[7] != 'T') {
    return 12;
  }

  EntLba   = Le64 (Hdr + 72);
  EntCount = Le32 (Hdr + 80);
  EntSize  = Le32 (Hdr + 84);
  if ((EntCount == 0) || (EntCount > 512) || (EntSize != 128)) {
    return 13;
  }

  Blocks = (EntCount * EntSize + UFS_BLOCK - 1) / UFS_BLOCK;
  Ents   = AllocatePool (Blocks * UFS_BLOCK);
  if (Ents == NULL) {
    return 14;
  }
  if (UfsReadBlocks (EntLba, Blocks, Ents) != 0) {
    FreePool (Ents);
    return 15;
  }

  for (I = 0; I < EntCount; I++) {
    CONST UINT8  *E = Ents + I * EntSize;
    UINT64       First;
    UINT64       Last;
    CHAR8        Part[17];
    UINTN        Len;

    First = Le64 (E + 32);
    Last  = Le64 (E + 40);
    if (First == 0) {
      continue;
    }
    ZeroMem (Part, sizeof (Part));
    for (J = 0; J < 16; J++) {
      UINT8  Hi = E[56 + 2 * J];

      Part[J] = (CHAR8)((Hi >= 32 && Hi < 127) ? Hi : 0);
      if (Part[J] == 0) {
        break;
      }
    }
    Len = AsciiStrLen (Part);
    if ((Len == 0) || (Len != AsciiStrLen (Name))) {
      continue;
    }
    if (AsciiStrCmp (Part, Name) == 0) {
      *FirstLba = First;
      *LastLba  = Last;
      FreePool (Ents);
      return 0;
    }
  }

  FreePool (Ents);
  return 16;
}
