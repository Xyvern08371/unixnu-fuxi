/** @file
  XnuLoad.c —— 从块设备（dtbo 分区）把 XNU payload 读进内存

  为什么不在 EFI 里内嵌内核：
    内核 15.8MB，把 Probe.efi 撑到 16MB 后 UEFI 加载它会崩（实测
    "Asynchronous Exception"）。所以改成：EFI 保持小体积，内核单独
    刷进 dtbo 分区（25MB），启动时读进来。

  分区镜像格式（tools/mkpayload_img.py 生成）：
      offset 0   "FUXIPAY1"
      offset 8   u64 长度
      offset 16  payload 数据
**/

#include <Uefi.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/BaseMemoryLib.h>
#include <Protocol/BlockIo.h>

#define PAYLOAD_MAGIC        "FUXIPAY1"
#define PAYLOAD_MIN_MEDIA    (16ULL * 1024 * 1024)   /* 分区至少 16MB */
#define PAYLOAD_MAX_MEDIA    (64ULL * 1024 * 1024)   /* 最多 64MB */

STATIC
BOOLEAN
MagicOk (
  IN CONST UINT8  *P
  )
{
  UINTN  I;

  for (I = 0; I < 8; I++) {
    if (P[I] != (UINT8)PAYLOAD_MAGIC[I]) {
      return FALSE;
    }
  }

  return TRUE;
}

/**
  在块设备里找 payload 并读进新分配的内存。

  @param[out] Buf   读到的缓冲（调用者负责 FreePool）
  @param[out] Size  长度

  @retval EFI_SUCCESS  找到并读成功
  @retval others       没找到
**/
typedef VOID (*XNU_LOG_FN)(CONST CHAR8 *Tag, UINT64 Value);


/* ---- 直接读 UFS（UEFI 没有块设备驱动时用这条路） ---- */
extern UINT32  UfsFindPartition (CONST CHAR8 *Name, UINT64 *FirstLba, UINT64 *LastLba);
extern UINT32  UfsReadBlocks (UINT64 Lba, UINT32 Count, VOID *Buf);

#define UFS_CHUNK_BLOCKS  16u     /* 每次 64KB，单个 PRDT 比较安全 */

/**
  从 UFS 的 dtbo 分区读 XNU payload。

  分区里是 tools/mkpayload_img.py 生成的镜像：
      "FUXIPAY1" + u64 长度 + payload
**/
EFI_STATUS
XnuLoadFromUfs (
  OUT VOID       **Buf,
  OUT UINTN      *Size,
  IN  XNU_LOG_FN  Log
  )
{
  UINT64        First = 0;
  UINT64        Last = 0;
  UINT32        Rc;
  UINT8         *Hdr;
  UINT64        Len = 0;
  UINT8         *Data;
  EFI_PHYSICAL_ADDRESS  Pages;
  UINT32        Done = 0;
  UINT32        Chunk;

  *Buf  = NULL;
  *Size = 0;

  Rc = UfsFindPartition ("dtbo", &First, &Last);
  if (Log != NULL) {
    Log ("UFS GPT", (UINT64)Rc);
  }
  if (Rc != 0) {
    return EFI_NOT_FOUND;
  }
  if (Log != NULL) {
    Log ("UFS DTBO LBA", First);
  }

  Hdr = AllocatePool (8192);
  if (Hdr == NULL) {
    return EFI_OUT_OF_RESOURCES;
  }
  if (UfsReadBlocks (First, 2, Hdr) != 0) {
    FreePool (Hdr);
    if (Log != NULL) {
      Log ("UFS READ ERR", 0);
    }
    return EFI_DEVICE_ERROR;
  }
  if (!MagicOk (Hdr)) {
    FreePool (Hdr);
    if (Log != NULL) {
      Log ("UFS MAGIC BAD", 0);
    }
    return EFI_NOT_FOUND;
  }
  CopyMem (&Len, Hdr + 8, sizeof (Len));
  FreePool (Hdr);

  if ((Len == 0) || (Len > 256ULL * 1024 * 1024)) {
    return EFI_NOT_FOUND;
  }

  Pages = 0;
  if (EFI_ERROR (gBS->AllocatePages (
                        AllocateAnyPages,
                        EfiLoaderData,
                        (UINTN)((Len + EFI_PAGE_SIZE - 1) / EFI_PAGE_SIZE),
                        &Pages
                        ))) {
    return EFI_OUT_OF_RESOURCES;
  }
  Data = (UINT8 *)(UINTN)Pages;

  /* 数据从分区偏移 16 字节开始；按块读再搬到 buffer */
  while (Done < (UINT32)Len) {
    UINT64  ByteOff = 16 + Done;
    UINT64  Lba = First + (ByteOff / UFS_CHUNK_BLOCKS / 4096) * 0;
    UINT32  InBlk;
    UINT8   *Tmp;
    UINT32  Want;

    /* 简化：payload 起始偏移 16 不是块对齐，所以从 first+0 开始按块读整段 */
    if (Done == 0) {
      Lba = First;
    }

    if (Log != NULL) {
      Log ("UFS CHUNK", (UINT64)Done);
    }

    Tmp = AllocatePool (UFS_CHUNK_BLOCKS * 4096);
    if (Tmp == NULL) {
      break;
    }

    /* 计算这一块覆盖的 LBA：从 first 起，第 (16+Done)/4096 块 */
    Lba = First + ((16 + Done) / 4096);
    InBlk = (UINT32)((16 + Done) % 4096);

    if (UfsReadBlocks (Lba, UFS_CHUNK_BLOCKS, Tmp) != 0) {
      FreePool (Tmp);
      break;
    }

    Want = (UINT32)Len - Done;
    Chunk = UFS_CHUNK_BLOCKS * 4096 - InBlk;
    if (Chunk > Want) {
      Chunk = Want;
    }
    CopyMem (Data + Done, Tmp + InBlk, Chunk);
    Done += Chunk;
    FreePool (Tmp);
  }

  if (Done != (UINT32)Len) {
    if (Log != NULL) {
      Log ("UFS SHORT", (UINT64)Done);
    }
    return EFI_DEVICE_ERROR;
  }

  if (Log != NULL) {
    Log ("UFS OK", (UINT64)Len);
  }
  *Buf  = Data;
  *Size = (UINTN)Len;
  return EFI_SUCCESS;
}

EFI_STATUS
XnuLoadFromBlock (
  OUT VOID       **Buf,
  OUT UINTN      *Size,
  IN  XNU_LOG_FN  Log
  )
{
  EFI_STATUS             Status;
  EFI_HANDLE             *Handles = NULL;
  UINTN                  Count = 0;
  UINTN                  I;
  EFI_BLOCK_IO_PROTOCOL  *Bio;
  UINT8                  *Hdr;
  UINT64                 Len;
  UINTN                  MediaSize;
  UINTN                  BlkSize;
  UINT8                  *Data;
  UINTN                  Off;
  UINTN                  Chunk;

  *Buf  = NULL;
  *Size = 0;

  Status = gBS->LocateHandleBuffer (
                  ByProtocol,
                  &gEfiBlockIoProtocolGuid,
                  NULL,
                  &Count,
                  &Handles
                  );
  if (EFI_ERROR (Status)) {
    if (Log != NULL) {
      Log ("BLK ERR", (UINT64)Status);
    }
    return Status;
  }

  if (Log != NULL) {
    Log ("BLK HANDLES", (UINT64)Count);
  }

  for (I = 0; I < Count; I++) {
    Bio = NULL;
    if (EFI_ERROR (gBS->HandleProtocol (Handles[I], &gEfiBlockIoProtocolGuid, (VOID **)&Bio))) {
      continue;
    }
    if ((Bio == NULL) || (Bio->Media == NULL) || !Bio->Media->MediaPresent) {
      continue;
    }
    if (Bio->Media->LastBlock == 0) {
      continue;
    }

    BlkSize   = Bio->Media->BlockSize;
    MediaSize = (UINTN)((Bio->Media->LastBlock + 1) * BlkSize);

    if ((Log != NULL) && (I < 6)) {
      Log ("BLK SIZE", (UINT64)MediaSize);
    }

    if ((MediaSize < PAYLOAD_MIN_MEDIA) || (MediaSize > PAYLOAD_MAX_MEDIA)) {
      continue;
    }

    /* 读第一块，看魔数 */
    Hdr = AllocatePool (BlkSize);
    if (Hdr == NULL) {
      continue;
    }
    Status = Bio->ReadBlocks (Bio, Bio->Media->MediaId, 0, BlkSize, Hdr);
    if (EFI_ERROR (Status) || !MagicOk (Hdr)) {
      FreePool (Hdr);
      continue;
    }
    CopyMem (&Len, Hdr + 8, sizeof (Len));
    FreePool (Hdr);

    if ((Len == 0) || (Len > MediaSize) || (Len > (256ULL * 1024 * 1024))) {
      continue;
    }

    {
      EFI_PHYSICAL_ADDRESS  Pages;

      Pages = 0;
      Status = gBS->AllocatePages (
                      AllocateAnyPages,
                      EfiLoaderData,
                      (UINTN)((Len + EFI_PAGE_SIZE - 1) / EFI_PAGE_SIZE),
                      &Pages
                      );
      if (EFI_ERROR (Status)) {
        if (Log != NULL) {
          Log ("ALLOC FAIL", (UINT64)Len);
        }
        continue;
      }
      Data = (UINT8 *)(UINTN)Pages;
    }

    /* 从偏移 16 开始按块读 */
    Off = 0;
    while (Off < (UINTN)Len) {
      UINT64  Lba = (16 + Off) / BlkSize;
      UINTN   InBlock = (16 + Off) % BlkSize;
      UINTN   Want = (UINTN)Len - Off;
      UINT8   *Tmp;

      Chunk = BlkSize;
      if (Want < Chunk) {
        Chunk = Want;
      }

      Tmp = AllocatePool (BlkSize);
      if (Tmp == NULL) {
        break;
      }
      Status = Bio->ReadBlocks (Bio, Bio->Media->MediaId, Lba, BlkSize, Tmp);
      if (EFI_ERROR (Status)) {
        FreePool (Tmp);
        break;
      }
      CopyMem (Data + Off, Tmp + InBlock, Chunk);
      FreePool (Tmp);
      Off += Chunk;
    }

    if (Off == (UINTN)Len) {
      if (Log != NULL) {
        Log ("BLK FOUND", (UINT64)Len);
      }
      *Buf  = Data;
      *Size = (UINTN)Len;
      FreePool (Handles);
      return EFI_SUCCESS;
    }

    FreePool (Data);
  }

  if (Handles != NULL) {
    FreePool (Handles);
  }
  if (Log != NULL) {
    Log ("BLK NOTFOUND", 0);
  }
  return EFI_NOT_FOUND;
}
