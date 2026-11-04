/** @file  Loader.c

  fuxi 引导器 —— M1 里程碑骨架 (在 Renegade UEFI 下运行的 UEFI Application)

  当前职责:
    1. 打开 ESP 上的 fuxi.dtb 与 payload.bin, 读进内存
    2. 打印当前异常等级 / 内存图 / 载荷地址
    3. (可选) ExitBootServices 后按交接约定跳转

  交接约定 (待真机验证, 见 docs/boot-chain.md):
    x0 = 设备树物理地址, 其余通用寄存器清零, MMU 状态由双方约定

  设计上刻意不用 UefiLib: 它的 Print() 背后拖着 DevicePathLib / HiiLib /
  UefiRuntimeServicesTableLib 一整串依赖, 在"单组件平台"里会把 DSC 拖崩。
  这里直接用 BasePrintLib + ConOut, 依赖只剩 BaseLib/PrintLib/MemoryAllocationLib。
**/

#include <Uefi.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/PrintLib.h>
#include <Protocol/LoadedImage.h>
#include <Protocol/SimpleFileSystem.h>
#include <Guid/FileInfo.h>

#define DT_NAME      L"\\fuxi.dtb"
#define PAYLOAD_NAME L"\\payload.bin"
#define MAX_LOAD     (64u * 1024u * 1024u)
#define LOG_BUF      512

/* GCC 开 LTO 时, 结构体拷贝/清零会被优化成 memcpy/memset 调用,
   而 EDK2 只提供 CopyMem/SetMem, 没有 libc。这里补三个兼容实现。
   注意: 必须用 CopyMem/SetMem 实现, 否则 -fno-builtin 下会自己调自己。 */
#if defined(__GNUC__)

VOID *
memcpy (
  OUT VOID        *Dest,
  IN  CONST VOID  *Src,
  IN  UINTN        Len
  )
{
  return CopyMem (Dest, (VOID *) Src, Len);
}

VOID *
memset (
  OUT VOID  *Dest,
  IN  INTN   Val,
  IN  UINTN  Len
  )
{
  return SetMem (Dest, Len, (UINT8) Val);
}

VOID *
memmove (
  OUT VOID        *Dest,
  IN  CONST VOID  *Src,
  IN  UINTN        Len
  )
{
  return CopyMem (Dest, (VOID *) Src, Len);
}

#endif

STATIC EFI_FILE_HANDLE gRootDir = NULL;

/* 兜底: Ubuntu 的 aarch64-linux-gnu-gcc 可能默认开启栈保护,
   而 EDK2 的运行时没有 __stack_chk_fail。DSC 里已经关了
   -fstack-protector, 这里再给一份空实现, 双保险。 */
#if defined(__GNUC__) && !defined(__clang__)
UINT64  __stack_chk_guard = 0x0A0B0C0D0E0F1011ULL;

VOID
__stack_chk_fail (
  VOID
  )
{
  for ( ; ; ) {
  }
}
#endif

/** 格式化后直接打到控制台, 不依赖 Boot Services 之外的任何库 */
STATIC
VOID
Log (
  IN CONST CHAR16  *Fmt,
  ...
  )
{
  VA_LIST  Args;
  CHAR16   Buf[LOG_BUF];

  VA_START (Args, Fmt);
  UnicodeVSPrint (Buf, sizeof (Buf), Fmt, Args);
  VA_END (Args);

  if (gST != NULL && gST->ConOut != NULL) {
    gST->ConOut->OutputString (gST->ConOut, Buf);
  }
}

STATIC
UINT64
CurrentEl (
  VOID
  )
{
  UINT64 Val;
  __asm__ __volatile__ ("mrs %0, CurrentEL" : "=r" (Val));
  return (Val >> 2) & 0x3;
}

STATIC
EFI_STATUS
OpenRoot (
  IN EFI_HANDLE ImageHandle
  )
{
  EFI_STATUS                       Status;
  EFI_LOADED_IMAGE_PROTOCOL       *Image;
  EFI_SIMPLE_FILE_SYSTEM_PROTOCOL *Fs;

  Status = gBS->HandleProtocol (ImageHandle, &gEfiLoadedImageProtocolGuid, (VOID **) &Image);
  if (EFI_ERROR (Status)) {
    return Status;
  }

  Status = gBS->HandleProtocol (Image->DeviceHandle, &gEfiSimpleFileSystemProtocolGuid, (VOID **) &Fs);
  if (EFI_ERROR (Status)) {
    return Status;
  }

  return Fs->OpenVolume (Fs, &gRootDir);
}

/** 读整个文件到 AllocatePages 得到的内存里 (物理地址可预测, 便于交接) */
STATIC
EFI_STATUS
ReadWholeFile (
  IN  CHAR16  *Name,
  OUT VOID   **Buffer,
  OUT UINTN   *Size
  )
{
  EFI_STATUS       Status;
  EFI_FILE_HANDLE  File;
  UINTN            InfoSize = 0;
  EFI_FILE_INFO   *Info = NULL;
  UINTN            Pages;

  Status = gRootDir->Open (gRootDir, &File, Name, EFI_FILE_MODE_READ, 0);
  if (EFI_ERROR (Status)) {
    return Status;
  }

  Status = File->GetInfo (File, &gEfiFileInfoGuid, &InfoSize, NULL);
  if (Status != EFI_BUFFER_TOO_SMALL) {
    File->Close (File);
    return EFI_LOAD_ERROR;
  }

  Info = AllocatePool (InfoSize);
  if (Info == NULL) {
    File->Close (File);
    return EFI_OUT_OF_RESOURCES;
  }

  Status = File->GetInfo (File, &gEfiFileInfoGuid, &InfoSize, Info);
  if (EFI_ERROR (Status) || Info->FileSize == 0 || Info->FileSize > MAX_LOAD) {
    FreePool (Info);
    File->Close (File);
    return EFI_LOAD_ERROR;
  }

  Pages  = EFI_SIZE_TO_PAGES ((UINTN) Info->FileSize);
  *Size  = Pages * EFI_PAGE_SIZE;
  Status = gBS->AllocatePages (AllocateAnyPages, EfiLoaderData, Pages,
                               (EFI_PHYSICAL_ADDRESS *) Buffer);
  FreePool (Info);
  if (EFI_ERROR (Status)) {
    File->Close (File);
    return Status;
  }

  ZeroMem (*Buffer, *Size);
  Status = File->Read (File, Size, *Buffer);
  File->Close (File);
  return Status;
}

STATIC
EFI_STATUS
LeaveBootServices (
  IN EFI_HANDLE ImageHandle
  )
{
  EFI_STATUS              Status = EFI_SUCCESS;
  UINTN                   MapSize = 0;
  UINTN                   MapKey;
  UINTN                   DescSize;
  UINT32                  DescVer;
  EFI_MEMORY_DESCRIPTOR  *Map = NULL;
  UINTN                   Try;

  for (Try = 0; Try < 4; Try++) {
    MapSize = 0;
    Status  = gBS->GetMemoryMap (&MapSize, Map, &MapKey, &DescSize, &DescVer);
    if (EFI_ERROR (Status) && Status != EFI_BUFFER_TOO_SMALL) {
      return Status;
    }
    if (Map != NULL) {
      FreePool (Map);
    }
    MapSize += 2 * DescSize;          /* 预留 GetMemoryMap 自身造成的变化 */
    Map      = AllocatePool (MapSize);
    if (Map == NULL) {
      return EFI_OUT_OF_RESOURCES;
    }
    Status = gBS->GetMemoryMap (&MapSize, Map, &MapKey, &DescSize, &DescVer);
    if (EFI_ERROR (Status)) {
      continue;
    }
    Status = gBS->ExitBootServices (ImageHandle, MapKey);
    if (!EFI_ERROR (Status)) {
      return EFI_SUCCESS;
    }
  }
  return Status;
}

STATIC
VOID
JumpToPayload (
  IN VOID    *Dt,
  IN UINT64   Entry
  )
{
  __asm__ __volatile__ (
    "msr  daifset, #0xf\n\t"      /* 关中断: 后面由 payload 自己接管 */
    "mov  x0, %0\n\t"
    "br   %1\n\t"
    :
    : "r" (Dt), "r" (Entry)
    : "x0"
    );
  __builtin_unreachable ();
}

EFI_STATUS
EFIAPI
UefiMain (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  EFI_STATUS  Status;
  VOID       *Dt          = NULL;
  UINTN       DtSize      = 0;
  VOID       *Payload     = NULL;
  UINTN       PayloadSize = 0;

  (VOID) SystemTable;

  Log (L"[fuxi-loader] boot, CurrentEL = EL%Lu\n", CurrentEl ());

  Status = OpenRoot (ImageHandle);
  if (EFI_ERROR (Status)) {
    Log (L"[fuxi-loader] cannot open ESP root: %r\n", Status);
    return Status;
  }

  Status = ReadWholeFile (DT_NAME, &Dt, &DtSize);
  if (EFI_ERROR (Status)) {
    Log (L"[fuxi-loader] read %s failed: %r\n", DT_NAME, Status);
    return Status;
  }
  Log (L"[fuxi-loader] DTB @ 0x%Lx (%Lu bytes)\n", (UINT64) (UINTN) Dt, (UINT64) DtSize);

  Status = ReadWholeFile (PAYLOAD_NAME, &Payload, &PayloadSize);
  if (EFI_ERROR (Status)) {
    Log (L"[fuxi-loader] no %s, self-check only: %r\n", PAYLOAD_NAME, Status);
    return EFI_SUCCESS;
  }
  Log (L"[fuxi-loader] payload @ 0x%Lx (%Lu bytes)\n",
       (UINT64) (UINTN) Payload, (UINT64) PayloadSize);

  Log (L"[fuxi-loader] ExitBootServices ...\n");
  Status = LeaveBootServices (ImageHandle);
  if (EFI_ERROR (Status)) {
    Log (L"[fuxi-loader] ExitBootServices failed: %r\n", Status);
    return Status;
  }

  /* 之后不能再调用任何 Boot Services, 包括 Log */
  JumpToPayload (Dt, (UINT64) (UINTN) Payload);
  return EFI_SUCCESS;
}
