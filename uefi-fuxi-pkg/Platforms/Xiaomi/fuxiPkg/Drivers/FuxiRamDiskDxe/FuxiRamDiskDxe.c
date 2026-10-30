/** @file
  Publish the FAT image that rides inside the firmware volume as a block device.

  Why this exists
  ---------------
  UFS is unusable on this board for now: SmemDxe reads 0x81D00000 and gets all
  zeroes, asserts on SMEM_READ_SMEM_4(&toc->version) == 1, and DebugAssert()
  parks the whole DXE dispatch in a dead loop. Every vendor driver upstream of
  UFS sits behind that same SMEM chain, so UFSDxe never gets a chance to bind.

  Nothing about booting XNU actually needs UFS, though. DarwinBoot only needs
  EFI_SIMPLE_FILE_SYSTEM_PROTOCOL to open "\kernel" and "\fuxi.adt". So the
  payload image (kernel + adt in FAT16) is carried inside the FD right behind
  the FV, and this driver republishes it as EFI_BLOCK_IO_PROTOCOL.
  DiskIoDxe, PartitionDxe and FatDxe then stack on top by themselves and hand
  DarwinBoot a normal SimpleFileSystem.

  Layout
  ------
    0xC0000000 + 0x00300000   firmware volume (the FD itself)
    0xC0300000 + 0x01100000   payload image, appended to the FD

  These match "UEFI FD" and "Payload Image" in MemoryMapLib and the FD size in
  Resources/Configs/fuxi.toml, so all of them have to move together.

  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#include <Uefi.h>
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/DebugLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiDriverEntryPoint.h>

#include <Protocol/BlockIo.h>
#include <Protocol/DevicePath.h>

#define PAYLOAD_BASE   0xC0300000ULL
#define PAYLOAD_SIZE   0x01100000ULL
#define BLOCK_SIZE     512U
#define LAST_BLOCK     ((UINT64)(PAYLOAD_SIZE / BLOCK_SIZE) - 1)

typedef struct {
  VENDOR_DEVICE_PATH          Vendor;
  EFI_DEVICE_PATH_PROTOCOL    End;
} FUXI_RAMDISK_DEVICE_PATH;

STATIC FUXI_RAMDISK_DEVICE_PATH  mDevicePath = {
  {
    { HARDWARE_DEVICE_PATH, HW_VENDOR_DP, { sizeof (VENDOR_DEVICE_PATH), 0 } },
    { 0x7D3A9C41, 0x2B6E, 0x4F08, { 0x9A, 0x13, 0x5C, 0x77, 0xE2, 0x40, 0x8B, 0x6D } }
  },
  { END_DEVICE_PATH_TYPE, END_ENTIRE_DEVICE_PATH_SUBTYPE, { sizeof (EFI_DEVICE_PATH_PROTOCOL), 0 } }
};

STATIC EFI_BLOCK_IO_MEDIA  mMedia = {
  0,                        // MediaId, filled in at entry
  FALSE,                    // RemovableMedia
  TRUE,                     // MediaPresent
  FALSE,                    // LogicalPartition
  TRUE,                     // ReadOnly -- the image is firmware, never written back
  FALSE,                    // WriteCaching
  BLOCK_SIZE,               // BlockSize
  1,                        // IoAlign
  0,                        // LastBlock, filled in at entry
  0,                        // LowestAlignedLba
  1                         // LogicalBlocksPerPhysicalBlock
};

STATIC
EFI_STATUS
EFIAPI
RamDiskReadBlocks (
  IN EFI_BLOCK_IO_PROTOCOL  *This,
  IN UINT32                 MediaId,
  IN EFI_LBA                Lba,
  IN UINTN                  BufferSize,
  OUT VOID                  *Buffer
  )
{
  UINT64  Offset;

  if (Buffer == NULL) {
    return EFI_INVALID_PARAMETER;
  }
  if (MediaId != This->Media->MediaId) {
    return EFI_MEDIA_CHANGED;
  }
  if ((BufferSize % BLOCK_SIZE) != 0) {
    return EFI_BAD_BUFFER_SIZE;
  }
  if ((Lba > This->Media->LastBlock) ||
      (BufferSize > (This->Media->LastBlock + 1 - Lba) * BLOCK_SIZE))
  {
    return EFI_INVALID_PARAMETER;
  }

  Offset = Lba * BLOCK_SIZE;
  CopyMem (Buffer, (VOID *)(UINTN)(PAYLOAD_BASE + Offset), BufferSize);
  return EFI_SUCCESS;
}

STATIC
EFI_STATUS
EFIAPI
RamDiskWriteBlocks (
  IN EFI_BLOCK_IO_PROTOCOL  *This,
  IN UINT32                 MediaId,
  IN EFI_LBA                Lba,
  IN UINTN                  BufferSize,
  IN VOID                   *Buffer
  )
{
  return EFI_WRITE_PROTECTED;
}

STATIC
EFI_STATUS
EFIAPI
RamDiskFlushBlocks (
  IN EFI_BLOCK_IO_PROTOCOL  *This
  )
{
  return EFI_SUCCESS;
}

STATIC
EFI_STATUS
EFIAPI
RamDiskReset (
  IN EFI_BLOCK_IO_PROTOCOL  *This,
  IN BOOLEAN                ExtendedVerification
  )
{
  return EFI_SUCCESS;
}

STATIC EFI_BLOCK_IO_PROTOCOL  mBlockIo = {
  EFI_BLOCK_IO_PROTOCOL_REVISION,
  &mMedia,
  RamDiskReset,
  RamDiskReadBlocks,
  RamDiskWriteBlocks,
  RamDiskFlushBlocks
};

EFI_STATUS
EFIAPI
FuxiRamDiskDxeEntry (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  EFI_STATUS  Status;
  EFI_HANDLE  Handle;
  UINT32      Signature;

  //
  // Refuse to publish garbage: a FAT boot sector starts with a jump
  // instruction (0xEB 0x??) and ends with the 0x55 0xAA signature.
  //
  Signature = ReadUnaligned32 ((VOID *)(UINTN)PAYLOAD_BASE);
  if ((Signature & 0xFF) != 0xEB) {
    DEBUG ((DEBUG_ERROR, "FuxiRamDisk: payload at 0x%lx is not FAT (0x%08x)\n",
            (UINT64)PAYLOAD_BASE, Signature));
    return EFI_NOT_FOUND;
  }

  mMedia.MediaId   = 0x46555849;   // 'FUXI'
  mMedia.LastBlock = (EFI_LBA)LAST_BLOCK;

  DEBUG ((DEBUG_ERROR, "FuxiRamDisk: %lu blocks of %u bytes at 0x%lx\n",
          (UINT64)(LAST_BLOCK + 1), BLOCK_SIZE, (UINT64)PAYLOAD_BASE));

  Handle = NULL;
  Status = gBS->InstallMultipleProtocolInterfaces (
                  &Handle,
                  &gEfiDevicePathProtocolGuid,
                  &mDevicePath,
                  &gEfiBlockIoProtocolGuid,
                  &mBlockIo,
                  NULL
                  );
  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_ERROR, "FuxiRamDisk: install failed %r\n", Status));
  }

  return Status;
}