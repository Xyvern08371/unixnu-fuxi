/** @file
  Show SMEM's version field as countable white cells at the bottom of the panel.

  SmemDxe dies on SMEM_READ_SMEM_4(&toc->version) == 1, reading the word at
  SMEM + 0xC0 (from its own disassembly: LDR w8, [x8, #0xC0]; CMP w8, #1).
  The region is readable - an earlier revision of this driver ran without
  faulting - so the only open question is what that word actually holds.

  The debug log scrolls over the top of the screen and would cover anything
  drawn there, so everything below goes near the bottom, well clear of it.

  Layout, top to bottom:

    1. a solid white block            -> proof this driver ran
    2. a strip of 40 dark cells       -> the ruler background
       with N of them repainted white -> N = the version word's value
    3. a 32-bit bar of the same word  -> one cell per bit, MSB left
    4. a solid white block            -> end marker

  Counting the white cells in strip 2 gives the version directly; if it ever
  exceeds 40 the bar in 3 gives the exact bits.

  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#include <Uefi.h>
#include <Library/BaseLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiDriverEntryPoint.h>

#define SMEM_BASE      0x81D00000ULL
#define VERSION_OFF    0xC0U
#define FB_BASE        0xB8000000ULL
#define FB_WIDTH       1080U
#define FB_HEIGHT      2400U
#define FB_BPP         4U
#define CELL           28U
#define RULER_CELLS    40U
#define ORIGIN_X       20U
#define STRIP_Y        1980U
#define BAR_Y          2030U

STATIC
VOID
FillCell (
  IN UINT32  X,
  IN UINT32  Y,
  IN UINT32  Size,
  IN UINT32  Pixel
  )
{
  UINT32  Row;
  UINT32  Col;
  UINT8   *Line;

  if ((X + Size > FB_WIDTH) || (Y + Size > FB_HEIGHT)) {
    return;
  }

  for (Row = 0; Row < Size; Row++) {
    Line = (UINT8 *)(UINTN)(FB_BASE + (UINTN)(Y + Row) * FB_WIDTH * FB_BPP + (UINTN)X * FB_BPP);
    for (Col = 0; Col < Size; Col++) {
      *(volatile UINT32 *)(Line + (UINTN)Col * FB_BPP) = Pixel;
    }
  }

  return;
}

EFI_STATUS
EFIAPI
FuxiSmemProbeEntry (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  CONST volatile UINT32  *Version;
  UINT32                 Value;
  UINT32                 Count;
  UINT32                 Bit;
  UINT32                 X;

  Version = (CONST volatile UINT32 *)(UINTN)(SMEM_BASE + VERSION_OFF);
  Value   = *Version;

  //
  // 1. ran marker
  //
  FillCell (ORIGIN_X, STRIP_Y - 70, 160, 0x00FFFFFFU);

  //
  // 2. ruler: dark strip, then repaint Value cells white (clamped to 40)
  //
  X = ORIGIN_X;
  for (Count = 0; Count < RULER_CELLS; Count++) {
    FillCell (X, STRIP_Y, CELL, 0x00101010U);
    X += CELL;
  }
  X = ORIGIN_X;
  Count = (Value > RULER_CELLS) ? RULER_CELLS : Value;
  for (Bit = 0; Bit < Count; Bit++) {
    FillCell (X, STRIP_Y, CELL, 0x00FFFFFFU);
    X += CELL;
  }

  //
  // 3. exact bits of the same word, MSB left
  //
  X = ORIGIN_X;
  for (Bit = 0; Bit < 32; Bit++) {
    UINT32  Set = (Value >> (31 - Bit)) & 1U;

    FillCell (X, BAR_Y, CELL, Set ? 0x00FFFFFFU : 0x00101010U);
    X += CELL;
  }

  //
  // 4. end marker
  //
  FillCell (ORIGIN_X, BAR_Y + CELL + 20, 160, 0x00FFFFFFU);

  return EFI_SUCCESS;
}
