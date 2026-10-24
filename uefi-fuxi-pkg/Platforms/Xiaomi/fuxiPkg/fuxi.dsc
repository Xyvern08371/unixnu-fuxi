##
#  Copyright (c) 2011 - 2022, ARM Limited. All rights reserved.
#  Copyright (c) 2014, Linaro Limited. All rights reserved.
#  Copyright (c) 2015 - 2020, Intel Corporation. All rights reserved.
#  Copyright (c) 2018, Bingxing Wang. All rights reserved.
#  Copyright (c) Microsoft Corporation.
#
#  SPDX-License-Identifier: BSD-2-Clause-Patent
##

################################################################################
#
# Defines Section - statements that will be processed to create a Makefile.
#
################################################################################
[Defines]
  PLATFORM_NAME                  = fuxi
  PLATFORM_GUID                  = A8854916-202A-456E-A74B-FF22ECB1FCF9
  PLATFORM_VERSION               = 0.1
  DSC_SPECIFICATION              = 0x00010005
  OUTPUT_DIRECTORY               = Build/fuxiPkg
  SUPPORTED_ARCHITECTURES        = AARCH64
  BUILD_TARGETS                  = RELEASE|DEBUG
  SKUID_IDENTIFIER               = DEFAULT
  FLASH_DEFINITION               = fuxiPkg/fuxi.fdf
  USE_CUSTOM_DISPLAY_DRIVER      = 0

  #
  # 0 = Mu drivers only. The previous stage's display keeps scanning out, so
  #     the boot manager is visible without any vendor hardware driver.
  # 1 = also load the stock vendor hardware drivers (SMEM, clocks, RPMh, UFS,
  #     USB, charger, ...). Their initialization currently blanks the panel.
  #
  SHENG_VENDOR_HW                = 0

  #
  # 0 = SM8550-AB
  # 1 = SM8550-AC
  #
  # Xiaomi 13 (fuxi/marble) uses SM8550-AB.
  SOC_TYPE                       = 0

!include KailuaPkg/KailuaPkg.dsc.inc

!if ($(USE_CUSTOM_DISPLAY_DRIVER) == 1) && ($(SHENG_VENDOR_HW) == 0)
  !error The stock DisplayDxe chain needs SHENG_VENDOR_HW = 1
!endif

[PcdsFixedAtBuild]
  #
  # Debug property mask.
  #
  # Bit 0 (DEBUG_PROPERTY_DEBUG_ASSERT_ENABLED) is cleared on purpose. The
  # stock vendor drivers assert on conditions this board does not satisfy yet,
  # and DebugAssert() spins forever, which stops the whole DXE dispatch before
  # BDS runs. With the bit clear, ASSERT() is a no-op, the driver returns an
  # error, and the rest of the firmware keeps going so the failure can be seen
  # on the panel instead of hanging it.
  #
  gEfiMdePkgTokenSpaceGuid.PcdDebugPropertyMask|0x26

  #
  # DDR Memory
  #
  gArmTokenSpaceGuid.PcdSystemMemoryBase|0x80000000

  #
  # UEFI Stack
  #
  gArmPlatformTokenSpaceGuid.PcdCPUCoresStackBase|0xC160D000
  gArmPlatformTokenSpaceGuid.PcdCPUCorePrimaryStackSize|0x40000

  #
  # SMBIOS
  #
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemManufacturer|"Xiaomi"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemModel|"Xiaomi 13"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemRetailModel|"fuxi"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemRetailSku|"Xiaomi_13_fuxi"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemBoardModel|"Xiaomi 13"

  #
  # Simple Frame Buffer
  #
  # Xiaomi 13 (fuxi/marble): 1080 x 2400, 32bpp BGRX.
  # Framebuffer base 0xB8000000 (GOP FrameBufferBase reported by ABL),
  # stride = width * 4 = 4320 bytes.
  #
  gSiliciumPkgTokenSpaceGuid.PcdFrameBufferWidth|1080
  gSiliciumPkgTokenSpaceGuid.PcdFrameBufferHeight|2400
  gSiliciumPkgTokenSpaceGuid.PcdFrameBufferColorDepth|32
  # Scale 3 gives ~56 lines of debug log. The log wraps to newest lines.
  gSiliciumPkgTokenSpaceGuid.PcdFrameBufferFontScale|3
  # Pause per log line so a video of the screen shows what loads last.
  gSiliciumPkgTokenSpaceGuid.PcdFrameBufferDelay|30000


  #
  # Platform PEI
  #
  gQcomPkgTokenSpaceGuid.PcdPlatformType|"LA"

[LibraryClasses]
  #
  # Memory Libraries
  #
  MemoryMapLib|fuxiPkg/Library/MemoryMapLib/MemoryMapLib.inf

  #
  # QCOM Libraries
  #
  ConfigurationMapLib|fuxiPkg/Library/ConfigurationMapLib/ConfigurationMapLib.inf

[Components]
  #
  # UniXNU + DarwinBoot
  #
  UniXNUPkg/Application/UniXNU/UniXNU.inf
  UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.inf
  fuxiPkg/Drivers/FuxiDisplayDepexDxe/FuxiDisplayDepexDxe.inf
  fuxiPkg/Drivers/FuxiGopLogDxe/FuxiGopLogDxe.inf
  # [off] fuxiPkg/Drivers/FuxiBootMemoryDxe/FuxiBootMemoryDxe.inf  -- faults at 0xB7DFE000; its DTB holes/initrd work is now covered by MemoryMapLib + FuxiRamDiskDxe
  fuxiPkg/Drivers/FuxiRamDiskDxe/FuxiRamDiskDxe.inf
  fuxiPkg/Drivers/FuxiKeyInputDxe/FuxiKeyInputDxe.inf
  DarwinBootPkg/Driver/DarwinBoot.inf

[LibraryClasses]
  UniXNULib|UniXNUPkg/Library/UniXNULib/UniXNULib.inf
  FdtLib|MdePkg/Library/BaseFdtLib/BaseFdtLib.inf
