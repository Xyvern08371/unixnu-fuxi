/** @file
  XnuBoot.c —— 从我们自己的 payload 启动 XNU（fuxi / SM8550）

  参考实现：dipa-studio/ios-sweet 的 shim/loader.c（骁龙 732G 上跑通 iOS 16）。

  payload 由 tools/mkpayload_fuxi.py 生成，布局：
      offset 0     magic "FUXIXNU" + 版本 + 段数
      0x10         virt_base, entry_va, adt_off, adt_size, kernel_end, phys_base, mem_size
      0x48         cmdline[608]
      0x2a8        段表（每项 32 字节：vmaddr, vmsize, file_off, file_size）
      之后          各段数据，最后是 Apple 设备树

  本模块做四件事：
    1. 按段把内核拷到 phys_base + (vmaddr - virt_base)
    2. 把 ADT 放在内核末尾，boot_args 放在 ADT 之后（16K 对齐）
    3. 填 boot_args（Revision/Version=2，Video 填 GOP 参数）
    4. 关闭 MMU/缓存，x0 = boot_args 物理地址，跳到 __start
**/

#include <Uefi.h>
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>   /* CopyMem */

#define PAYLOAD_MAGIC      "FUXIXNU"
#define BOOT_LINE_LENGTH   608
#define PAYLOAD_CMDLINE    0x48
#define PAYLOAD_SEGTAB     0x2a8
#define PAGE_16K           0x4000ULL

/* payload 由 CI 生成的 xnu_payload.S 以 .incbin 方式嵌入 */
typedef VOID (*XNU_LOG_FN)(CONST CHAR8 *Tag, UINT64 Value);

extern UINT64      mXnuPhysBase;
extern UINT64      mXnuPhysSize;
extern UINT32      XnuPatchAdt (UINT8 *Adt, UINTN Len, UINT64 Base, UINT64 Size);

extern CONST UINT8  gXnuPayload[];
extern CONST UINT8  gXnuPayloadEnd[];

/** 返回内嵌 payload 的字节数（0 = 没嵌入） */
UINTN
XnuPayloadSize (
  VOID
  )
{
  UINTN  N;

  N = (UINTN)(gXnuPayloadEnd - gXnuPayload);
  /* 占位 .S 可能残留几个字节；小于段表偏移的都当作没有内嵌 */
  return (N < 0x300) ? 0 : N;
}

/** 返回内嵌 payload 的地址 */
CONST VOID *
XnuPayloadAddr (
  VOID
  )
{
  return (CONST VOID *)gXnuPayload;
}

VOID
AsmXnuDcacheCleanRange (
  IN UINTN  Start,
  IN UINTN  End
  );

VOID
AsmXnuDcacheInvalidateRange (
  IN UINTN  Start,
  IN UINTN  End
  );

VOID
AsmXnuTryMmuOff (
  OUT UINT64  Out[2]
  );

VOID
AsmXnuJump (
  IN UINTN  EntryPa,
  IN UINTN  BootArgsPa
  );

typedef struct {
  UINT64  VmAddr;
  UINT64  VmSize;
  UINT64  FileOff;
  UINT64  FileSize;
} PAYLOAD_SEG;

typedef struct {
  UINT64  BaseAddr;
  UINT64  Display;
  UINT64  RowBytes;
  UINT64  Width;
  UINT64  Height;
  UINT64  Depth;
} BOOT_VIDEO;

typedef struct {
  UINT16      Revision;
  UINT16      Version;
  UINT64      VirtBase;
  UINT64      PhysBase;
  UINT64      MemSize;
  UINT64      TopOfKernelData;
  BOOT_VIDEO  Video;
  UINT32      MachineType;
  UINT64      DeviceTreeP;
  UINT32      DeviceTreeLength;
  CHAR8       CommandLine[BOOT_LINE_LENGTH];
  UINT64      BootFlags;
  UINT64      MemSizeActual;
} XNU_BOOT_ARGS;

/* MMU 关掉之后所有访问都是 Device 内存，必须按 8 字节对齐逐字拷贝 */
STATIC
VOID
Copy64 (
  IN UINTN  Dst,
  IN UINTN  Src,
  IN UINTN  Len
  )
{
  volatile UINT64  *D = (volatile UINT64 *)Dst;
  volatile UINT64  *S = (volatile UINT64 *)Src;
  UINTN            N = (Len + 7) / 8;
  UINTN            I;

  for (I = 0; I < N; I++) {
    D[I] = S[I];
  }
}

STATIC
VOID
Zero64 (
  IN UINTN  Dst,
  IN UINTN  Len
  )
{
  volatile UINT64  *D = (volatile UINT64 *)Dst;
  UINTN            I;

  for (I = 0; I < Len / 8; I++) {
    D[I] = 0;
  }
}

STATIC
BOOLEAN
MagicOk (
  IN CONST CHAR8  *M
  )
{
  UINTN  I;

  for (I = 0; I < 8; I++) {
    if (M[I] != PAYLOAD_MAGIC[I]) {
      return FALSE;
    }
  }

  return TRUE;
}

/**
  启动 XNU。

  @param[in] Payload     payload 起始地址（可以是被拷到内存里的副本）
  @param[in] PayloadLen  payload 长度
  @param[in] FbBase      帧缓冲物理基址（GOP）
  @param[in] FbPitch     行字节数
  @param[in] FbWidth     宽度
  @param[in] FbHeight    高度

  @return 正常情况下不返回（直接跳进 XNU）
**/
VOID
XnuBootRun (
  IN CONST VOID  *Payload,
  IN UINTN       PayloadLen,
  IN UINTN       FbBase,
  IN UINTN       FbPitch,
  IN UINT32      FbWidth,
  IN UINT32      FbHeight,
  IN XNU_LOG_FN  Log
  )
{
  CONST UINT8    *P = (CONST UINT8 *)Payload;
  CONST UINT64   *Hdr = (CONST UINT64 *)(P + 0x10);
  UINT64         VirtBase;
  UINT64         EntryVa;
  UINT64         AdtOff;
  UINT64         AdtSize;
  UINT64         KernelEnd;
  UINT64         PhysBase;
  UINT64         MemSize;
  UINT32         NSegs;
  UINT64         PaOfVa;
  UINT64         AdtPa;
  UINT64         BaPa;
  UINT64         Top;
  UINTN          I;
  XNU_BOOT_ARGS  *Ba;

  if (Log != NULL) {
    Log ("PAYLEN", (UINT64)PayloadLen);
  }

  if ((Payload == NULL) || (PayloadLen < PAYLOAD_SEGTAB) || !MagicOk ((CONST CHAR8 *)P)) {
    if (Log != NULL) {
      Log ("BAD MAGIC", 0);
    }
    return;
  }

  NSegs     = *(CONST UINT32 *)(P + 12);
  VirtBase  = Hdr[0];
  EntryVa   = Hdr[1];
  AdtOff    = Hdr[2];
  AdtSize   = Hdr[3];
  KernelEnd = Hdr[4];
  PhysBase  = Hdr[5];
  MemSize   = Hdr[6];
  /* 用 EFI 内存图挑出来的真实可用内存覆盖 ADT 里的硬编码值 */
  if (mXnuPhysBase != 0) {
    PhysBase = mXnuPhysBase;
    MemSize  = mXnuPhysSize;
    if (Log != NULL) {
      Log ("USE PICKED", PhysBase);
    }
  }

  PaOfVa    = PhysBase - VirtBase;

  if (Log != NULL) {
    Log ("VIRTBASE", VirtBase);
    Log ("PHYSBASE", PhysBase);
    Log ("KEND", KernelEnd);
    Log ("ADTSIZE", AdtSize);
    Log ("ENTRY", EntryVa);
    Log ("NSEGS", NSegs);
  }

  /* 1. 各段拷到 phys_base + (vmaddr - virt_base) */
  {
    CONST PAYLOAD_SEG  *Seg = (CONST PAYLOAD_SEG *)(P + PAYLOAD_SEGTAB);

    for (I = 0; I < NSegs; I++) {
      UINT64  Dst = Seg[I].VmAddr + PaOfVa;

      Copy64 ((UINTN)Dst, (UINTN)(P + Seg[I].FileOff), (UINTN)Seg[I].FileSize);
      if (Seg[I].VmSize > Seg[I].FileSize) {
        Zero64 ((UINTN)Dst + (UINTN)Seg[I].FileSize, (UINTN)(Seg[I].VmSize - Seg[I].FileSize));
      }
    }
  }

  if (Log != NULL) {
    Log ("SEGS DONE", 0);
  }

  /* 2. ADT 放内核末尾，boot_args 放 ADT 之后（16K 对齐） */
  AdtPa = KernelEnd + PaOfVa;
  Copy64 ((UINTN)AdtPa, (UINTN)(P + AdtOff), (UINTN)AdtSize);

  /* 把 ADT 里的 dram-base/dram-size 改成实际使用的那块内存 */
  {
    UINT32  Patched;

    Patched = XnuPatchAdt ((UINT8 *)(UINTN)AdtPa, (UINTN)AdtSize, PhysBase, MemSize);
    if (Log != NULL) {
      Log ("ADT PATCHED", (UINT64)Patched);
    }
  }

  BaPa = (AdtPa + AdtSize + PAGE_16K - 1) & ~(PAGE_16K - 1);
  Top  = BaPa + PAGE_16K;
  Zero64 ((UINTN)BaPa, PAGE_16K);

  if (Log != NULL) {
    Log ("ADT DONE", AdtPa);
  }

  /* 3. 填 boot_args */
  Ba                    = (XNU_BOOT_ARGS *)(UINTN)BaPa;
  Ba->Revision          = 2;
  Ba->Version           = 2;
  Ba->VirtBase          = VirtBase;
  Ba->PhysBase          = PhysBase;
  Ba->MemSize           = MemSize;
  Ba->TopOfKernelData   = Top;
  Ba->Video.BaseAddr    = FbBase;
  Ba->Video.Display     = 1;
  Ba->Video.RowBytes    = FbPitch;
  Ba->Video.Width       = FbWidth;
  Ba->Video.Height      = FbHeight;
  Ba->Video.Depth       = 32;
  /* XNU 读设备树时 MMU 已开，所以这里必须给虚拟地址 */
  Ba->DeviceTreeP       = AdtPa - PaOfVa;
  Ba->DeviceTreeLength  = (UINT32)AdtSize;
  Ba->MemSizeActual     = MemSize;

  CopyMem (Ba->CommandLine, P + PAYLOAD_CMDLINE, BOOT_LINE_LENGTH);
  Ba->CommandLine[BOOT_LINE_LENGTH - 1] = 0;

  if (Log != NULL) {
    Log ("BOOTARGS", BaPa);
  }

  /* 4. 按范围清 D-cache，然后关 MMU/缓存并跳 __start（x0 = boot_args） */
  AsmXnuDcacheCleanRange ((UINTN)PhysBase, (UINTN)(KernelEnd + PaOfVa));
  AsmXnuDcacheCleanRange ((UINTN)AdtPa, (UINTN)(AdtPa + AdtSize));
  AsmXnuDcacheCleanRange ((UINTN)BaPa, (UINTN)(BaPa + PAGE_16K));

  /* 跳之前把入口地址和那里的头 8 字节打出来：确认那儿真的是代码 */
  {
    UINT64  EntryPa = EntryVa + PaOfVa;
    UINT64  Head;

  {
    volatile UINT32  *Fb = (volatile UINT32 *)FbBase;
    UINTN             Pixels = (UINTN)FbPitch * (UINTN)FbHeight;   // FbPitch 单位是像素，不要再除 4
    UINTN             k;

    for (k = 0; k < Pixels; k++) {
      Fb[k] = 0xFFFF00FFU;
    }

    /*
     * 关键：帧缓冲是可缓存映射，刚写的这批还在 cache 里（脏）。
     * 先回写到显存、再作废这些行，否则内核（关 MMU 后直接写 DRAM）
     * 画的颜色会被这些迟到逐出的脏行盖回品红。
     */
    AsmXnuDcacheCleanRange ((UINTN)FbBase, (UINTN)FbBase + Pixels * 4);
    AsmXnuDcacheInvalidateRange ((UINTN)FbBase, (UINTN)FbBase + Pixels * 4);
    if (Log != NULL) {
      Log ("JUMPING", EntryVa + PaOfVa);
    }
  }

    /*
     * 验证 MMU 到底能不能关：如果 EL2 上有 hypervisor 设了 HCR_EL2.TVM，
     * EL1 写 SCTLR_EL1 会被静默忽略，那么后面 br 到物理地址就会失败。
     */
    {
      UINT64  Mm[2];

      AsmXnuTryMmuOff (Mm);
      if (Log != NULL) {
        Log ("SCTLR BEFORE", Mm[0]);
        Log ("SCTLR AFTER", Mm[1]);
        Log ("MMU CAN OFF", (Mm[1] & 1ULL) == 0 ? 1 : 0);
      }
    }

    CopyMem (&Head, (VOID *)(UINTN)EntryPa, 8);
    if (Log != NULL) {
      Log ("ENTRY PA", EntryPa);
      Log ("CODE@ENTRY", Head);

      /* 自校验：作废内核区的 D-cache 行，再从内存重读同样的 8 字节 */
      AsmXnuDcacheInvalidateRange ((UINTN)PhysBase, (UINTN)(KernelEnd + PaOfVa));
      {
        UINT64  Head2;

        CopyMem (&Head2, (VOID *)(UINTN)EntryPa, 8);
        Log ("CODE@MEM", Head2);
      }
    }
  }

  /*
   * 最后一步的探针：整屏刷成品红 + 打一行 JUMPING，然后才跳。
   * 看到品红+JUMPING = 段拷贝/ADT/boot_args/清缓存全部走完，正准备跳。
   */

  AsmXnuJump ((UINTN)(EntryVa + PaOfVa), (UINTN)BaPa);
}
