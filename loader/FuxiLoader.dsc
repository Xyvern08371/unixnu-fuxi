## @file
#  FuxiLoader 平台描述文件
#
#  用法(在 edk2 源码树里, PACKAGES_PATH 指向本仓库根):
#    export PACKAGES_PATH=$PWD:$PWD/..
#    build -p ../loader/FuxiLoader.dsc -a AARCH64 -t GCC5 -b RELEASE
#
#  说明: 这是"单组件平台", 只为编出一个 EFI Application。
#  只保留 Loader.c 真正用到的库 —— 多余条目会在编译期报"找不到"或浪费排查时间。
##

[Defines]
  PLATFORM_NAME                  = FuxiLoader
  PLATFORM_GUID                  = 3f9c1a52-6b47-4a1e-9c8d-2f4e7b1a6d05
  PLATFORM_VERSION               = 0.1
  DSC_SPECIFICATION              = 0x00010005
  OUTPUT_DIRECTORY               = Build/FuxiLoader
  SUPPORTED_ARCHITECTURES        = AARCH64
  BUILD_TARGETS                  = DEBUG|RELEASE
  SKUID_IDENTIFIER               = DEFAULT

[LibraryClasses]
  BaseLib|MdePkg/Library/BaseLib/BaseLib.inf
  BaseMemoryLib|MdePkg/Library/BaseMemoryLib/BaseMemoryLib.inf
  DebugLib|MdePkg/Library/BaseDebugLibNull/BaseDebugLibNull.inf
  PrintLib|MdePkg/Library/BasePrintLib/BasePrintLib.inf
  PcdLib|MdePkg/Library/BasePcdLibNull/BasePcdLibNull.inf
  MemoryAllocationLib|MdePkg/Library/UefiMemoryAllocationLib/UefiMemoryAllocationLib.inf
  UefiBootServicesTableLib|MdePkg/Library/UefiBootServicesTableLib/UefiBootServicesTableLib.inf
  UefiApplicationEntryPoint|MdePkg/Library/UefiApplicationEntryPoint/UefiApplicationEntryPoint.inf

[BuildOptions]
  # Ubuntu 的 aarch64-linux-gnu-gcc 默认开着 -fstack-protector-strong,
  # 而 EDK2 不提供 __stack_chk_fail, 链接会炸。
  GCC:*_*_AARCH64_CC_FLAGS = -fno-stack-protector

[Components]
  loader/FuxiLoader.inf
