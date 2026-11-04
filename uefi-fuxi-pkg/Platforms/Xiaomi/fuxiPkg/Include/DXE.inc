  INF MdeModulePkg/Core/Dxe/DxeMain.inf
  INF MdeModulePkg/Universal/PCD/Dxe/Pcd.inf

!if $(SHENG_VENDOR_HW) == 1
  # EnvDxe returns EFI_NOT_FOUND right after PcdDxe on fuxi and BDS stalls there.
  # INF Binaries/marble/QcomPkg/Drivers/EnvDxe/EnvDxe.inf
!endif

  INF MdeModulePkg/Universal/ReportStatusCodeRouter/RuntimeDxe/ReportStatusCodeRouterRuntimeDxe.inf
  INF MdeModulePkg/Universal/StatusCodeHandler/RuntimeDxe/StatusCodeHandlerRuntimeDxe.inf
  INF ArmPkg/Drivers/CpuDxe/CpuDxe.inf
  INF MdeModulePkg/Core/RuntimeDxe/RuntimeDxe.inf
  INF MdeModulePkg/Universal/SecurityStubDxe/SecurityStubDxe.inf

!if $(SHENG_VENDOR_HW) == 1
  # INF Binaries/marble/QcomPkg/Drivers/ShmBridgeDxe/ShmBridgeDxeLA.inf
  # INF Binaries/marble/QcomPkg/Drivers/TzDxe/ScmDxeLA.inf
  # INF Binaries/marble/QcomPkg/Drivers/TzDxe/TzDxeLA.inf
!endif

  INF MdeModulePkg/Universal/WatchdogTimerDxe/WatchdogTimer.inf
  INF MdeModulePkg/Universal/CapsuleRuntimeDxe/CapsuleRuntimeDxe.inf
  INF MdeModulePkg/Universal/Variable/RuntimeDxe/VariableRuntimeDxe.inf
  INF EmbeddedPkg/EmbeddedMonotonicCounter/EmbeddedMonotonicCounter.inf
  INF MdeModulePkg/Universal/ResetSystemRuntimeDxe/ResetSystemRuntimeDxe.inf
  INF EmbeddedPkg/RealTimeClockRuntimeDxe/RealTimeClockRuntimeDxe.inf
  INF EmbeddedPkg/MetronomeDxe/MetronomeDxe.inf
  INF MdeModulePkg/Universal/HiiDatabaseDxe/HiiDatabaseDxe.inf
  INF ArmPkg/Drivers/ArmGicDxe/ArmGicDxe.inf
  INF ArmPkg/Drivers/TimerDxe/TimerDxe.inf

!if $(SHENG_VENDOR_HW) == 1
  # INF Binaries/marble/QcomPkg/Drivers/ChipInfoDxe/ChipInfoDxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/IPCCDxe/IPCCDxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/GLinkDxe/GLinkDxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/PlatformInfoDxe/PlatformInfoDxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/ProjectInfoDxe/ProjectInfoDxe.inf
  INF Binaries/marble/QcomPkg/Drivers/DALSYSDxe/DALSYSDxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/HALIOMMUDxe/HALIOMMUDxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/HWIODxe/HWIODxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/I2CDxe/I2CDxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/TLMMDxe/TLMMDxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/PmicDxe/PmicDxeLa.inf
!endif

  INF MdeModulePkg/Universal/DevicePathDxe/DevicePathDxe.inf
  # [off] INF fuxiPkg/Drivers/FuxiBootMemoryDxe/FuxiBootMemoryDxe.inf  -- faults at 0xB7DFE000; its DTB holes/initrd work is now covered by MemoryMapLib + FuxiRamDiskDxe
  INF fuxiPkg/Drivers/FuxiKeyInputDxe/FuxiKeyInputDxe.inf
  INF fuxiPkg/Drivers/FuxiRamDiskDxe/FuxiRamDiskDxe.inf
  # The XNU loader is part of the firmware: a driver loaded from a volume is
  # refused by the image verification of this build.
  INF DarwinBootPkg/Driver/DarwinBoot.inf
  INF MdeModulePkg/Universal/Disk/DiskIoDxe/DiskIoDxe.inf
  INF MdeModulePkg/Universal/Disk/PartitionDxe/PartitionDxe.inf
  INF FatPkg/EnhancedFatDxe/Fat.inf
  INF MdeModulePkg/Universal/Disk/UnicodeCollation/EnglishDxe/EnglishDxe.inf

!if $(SHENG_VENDOR_HW) == 1
  INF Binaries/marble/QcomPkg/Drivers/UFSDxe/UFSDxe.inf
  INF Binaries/marble/QcomPkg/Drivers/CmdDbDxe/CmdDbDxe.inf
  INF Binaries/marble/QcomPkg/Drivers/PwrUtilsDxe/PwrUtilsDxe.inf
  INF Binaries/marble/QcomPkg/Drivers/RpmhDxe/RpmhDxe.inf
  INF Binaries/marble/QcomPkg/Drivers/NpaDxe/NpaDxe.inf
  INF Binaries/marble/QcomPkg/Drivers/ULogDxe/ULogDxe.inf
  INF Binaries/marble/QcomPkg/Drivers/VcsDxe/VcsDxe.inf
  INF Binaries/marble/QcomPkg/Drivers/ClockDxe/ClockDxe.inf
  INF Binaries/marble/QcomPkg/Drivers/SPMIDxe/SPMIDxe.inf
  INF Binaries/marble/QcomPkg/Drivers/ICBDxe/ICBDxe.inf
  INF Binaries/marble/QcomPkg/Drivers/SmemDxe/SmemDxe.inf
!endif
  INF MdeModulePkg/Universal/BdsDxe/BdsDxe.inf

!if $(SHENG_VENDOR_HW) == 1
  # INF Binaries/marble/QcomPkg/Drivers/RscDxe/RscDxe.inf
!endif

  INF EmbeddedPkg/SimpleTextInOutSerial/SimpleTextInOutSerial.inf
  INF MdeModulePkg/Universal/PrintDxe/PrintDxe.inf
  INF MdeModulePkg/Universal/Console/ConPlatformDxe/ConPlatformDxe.inf
  INF MdeModulePkg/Universal/Console/ConSplitterDxe/ConSplitterDxe.inf
  INF MdeModulePkg/Universal/Console/GraphicsConsoleDxe/GraphicsConsoleDxe.inf

  # Headless until stock sheng framebuffer data is available.
!if $(SHENG_VENDOR_HW) == 1
  # INF Binaries/marble/QcomPkg/Drivers/GpiDxe/GpiDxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/SPIDxe/SPIDxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/SdccDxe/SdccDxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/FeatureEnablerDxe/FeatureEnablerDxe.inf

  # USE_CUSTOM_DISPLAY_DRIVER = 1: stock sheng display chain (board DEPEX glue,
  # unchanged vendor DisplayDxe with the N81A panel data from RAW.inc).
  # Otherwise SimpleFbDxe publishes a GOP on the frame buffer the previous
  # stage left scanning out.
!endif
!if $(USE_CUSTOM_DISPLAY_DRIVER) == 1
  INF fuxiPkg/Drivers/FuxiGopLogDxe/FuxiGopLogDxe.inf
  INF fuxiPkg/Drivers/FuxiDisplayDepexDxe/FuxiDisplayDepexDxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/DisplayDxe/DisplayDxe.inf
!else
  INF SiliciumPkg/Drivers/SimpleFbDxe/SimpleFbDxe.inf
!endif

  # Headless until stock sheng framebuffer data is available.

!if $(SHENG_VENDOR_HW) == 1
  # INF Binaries/marble/QcomPkg/Drivers/ButtonsDxe/ButtonsDxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/ChargerExDxe/ChargerExDxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/PmicGlinkDxe/PmicGlinkDxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/QcomChargerDxe/QcomChargerDxeLA.inf
  # INF Binaries/marble/QcomPkg/Drivers/UsbPwrCtrlDxe/UsbPwrCtrlDxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/TsensDxe/TsensDxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/LimitsDxe/LimitsDxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/DDRInfoDxe/DDRInfoDxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/UsbfnDwc3Dxe/UsbfnDwc3Dxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/XhciPciEmulationDxe/XhciPciEmulationDxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/XhciDxe/XhciDxe.inf
!endif

  INF MdeModulePkg/Bus/Usb/UsbBusDxe/UsbBusDxe.inf
  INF MdeModulePkg/Bus/Usb/UsbKbDxe/UsbKbDxe.inf
  INF MdeModulePkg/Bus/Usb/UsbMassStorageDxe/UsbMassStorageDxe.inf

!if $(SHENG_VENDOR_HW) == 1
  # INF Binaries/marble/QcomPkg/Drivers/UsbMsdDxe/UsbMsdDxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/UsbDeviceDxe/UsbDeviceDxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/UsbConfigDxe/UsbConfigDxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/UsbInitDxe/UsbInitDxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/UCDxe/UCDxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/RNGDxe/RngDxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/PILDxe/PILDxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/PILProxyDxe/PILProxyDxe.inf
  # INF Binaries/marble/QcomPkg/Drivers/SPSSDxe/SPSSDxe.inf
!endif
