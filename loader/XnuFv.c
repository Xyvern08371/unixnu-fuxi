/** @file
  XnuLoad.c 追加：从固件卷（FV）里读 RAW section 形式的 payload

  为什么用这条路：
    · 这版固件没有 UFS DXE 驱动 → EFI_BLOCK_IO 一个设备都没有
    · 直接读 UFS MMIO（0x1d84000）→ 该区域没映射，同步异常
    · 把 payload 当"模块"编进 EFI → 16MB 模块 UEFI 加载会崩

  固件卷里的 RAW section 是 UEFI 原生支持的：由 ABL/FV 解压到内存，
  用 FirmwareVolume2 协议按 GUID 取指针，不需要任何存储驱动。
**/

#include <Uefi.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/BaseMemoryLib.h>
#include <Protocol/FirmwareVolume2.h>

typedef VOID (*XNU_LOG_FN)(CONST CHAR8 *Tag, UINT64 Value);

/* 与 FDF 里 FILE FREEFORM 的 GUID 保持一致 */
STATIC EFI_GUID  mXnuPayloadGuid = {
  0x9f3c7a21, 0x5b4e, 0x4c8d, { 0x9a, 0x11, 0x7e, 0x2b, 0x63, 0x08, 0xd4, 0x51 }
};

STATIC
BOOLEAN
MagicOk2 (
  IN CONST UINT8  *P
  )
{
  return (P[0] == 'F') && (P[1] == 'U') && (P[2] == 'X') && (P[3] == 'I') &&
         (P[4] == 'P') && (P[5] == 'A') && (P[6] == 'Y') && (P[7] == '1');
}

/**
  从固件卷里取 payload。

  @param[out] Buf   payload 指针（指向 FV 内的数据，无需释放）
  @param[out] Size  长度
**/
EFI_STATUS
XnuLoadFromFv (
  OUT VOID       **Buf,
  OUT UINTN      *Size,
  IN  XNU_LOG_FN  Log
  )
{
  EFI_STATUS                      Status;
  EFI_HANDLE                      *Handles = NULL;
  UINTN                           Count = 0;
  UINTN                           I;
  EFI_FIRMWARE_VOLUME2_PROTOCOL   *Fv;
  VOID                            *Data;
  UINTN                           DataSize;
  UINT32                          AuthStatus;
  EFI_FV_FILETYPE                 FileType;

  *Buf  = NULL;
  *Size = 0;

  Status = gBS->LocateHandleBuffer (
                  ByProtocol,
                  &gEfiFirmwareVolume2ProtocolGuid,
                  NULL,
                  &Count,
                  &Handles
                  );
  if (EFI_ERROR (Status)) {
    if (Log != NULL) {
      Log ("FV NO HANDLE", (UINT64)Status);
    }
    return Status;
  }
  if (Log != NULL) {
    Log ("FV HANDLES", (UINT64)Count);
  }

  for (I = 0; I < Count; I++) {
    Fv = NULL;
    if (EFI_ERROR (gBS->HandleProtocol (Handles[I], &gEfiFirmwareVolume2ProtocolGuid, (VOID **)&Fv))) {
      continue;
    }
    if (Fv == NULL) {
      continue;
    }

    Data      = NULL;
    DataSize  = 0;
    AuthStatus = 0;
    FileType   = 0;
    Status = Fv->ReadSection (
                   Fv,
                   &mXnuPayloadGuid,
                   EFI_SECTION_RAW,
                   0,
                   &Data,
                   &DataSize,
                   &AuthStatus
                   );
    if (EFI_ERROR (Status) || (Data == NULL) || (DataSize < 0x300)) {
      continue;
    }

    if (Log != NULL) {
      Log ("FV PAYLOAD", (UINT64)DataSize);
    }

    /* FDF 里放的是 mkpayload_img.py 的格式：magic + u64 长度 + payload */
    if (MagicOk2 ((CONST UINT8 *)Data)) {
      UINT64  Len;

      CopyMem (&Len, (UINT8 *)Data + 8, sizeof (Len));
      if ((Len > 0) && (Len <= DataSize - 16)) {
        *Buf  = (UINT8 *)Data + 16;
        *Size = (UINTN)Len;
        if (Log != NULL) {
          Log ("FV OK", (UINT64)Len);
        }
        FreePool (Handles);
        return EFI_SUCCESS;
      }
    }

    /* 不是那个格式，就整块当 payload */
    *Buf  = Data;
    *Size = DataSize;
    if (Log != NULL) {
      Log ("FV RAW", (UINT64)DataSize);
    }
    FreePool (Handles);
    return EFI_SUCCESS;
  }

  FreePool (Handles);
  if (Log != NULL) {
    Log ("FV NOTFOUND", 0);
  }
  return EFI_NOT_FOUND;
}
