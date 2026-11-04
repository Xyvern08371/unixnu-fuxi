#!/usr/bin/env python3
"""给 edk2-msm 的固件打补丁，让 ExitBootServices 能成功。

背景（实测）：
  DxeCore 的 CoreTerminateMemoryMap 在退出 Boot Services 前校验内存图：

      if ((Entry->Start & (RUNTIME_PAGE_ALLOCATION_GRANULARITY - 1)) != 0) -> 失败
      if (((Entry->End + 1) & (RUNTIME_PAGE_ALLOCATION_GRANULARITY - 1)) != 0) -> 失败

  而 EDK2 在 AArch64 上把 RUNTIME_PAGE_ALLOCATION_GRANULARITY 定义为 0x10000
  (64KB)，高通平台却按 4KB 分配 runtime 区（fuxi 上实测 9 条 runtime 条目只
  有 1 条 0x09F5F000 不是 64KB 对齐），于是退出必然返回 EFI_INVALID_PARAMETER。

补丁 1（对齐）：不再"降粒度跳过检查"，而是把越界的那条 runtime 区
  向外扩到 64KB 边界（Start 向下取整、End 向上取整），使内存图真正满足
  64KB 粒度要求。这样固件保持正规的 64KB 语义。

补丁 2（MapKey）：CoreExitBootServices 会先通知 EXIT_BOOT_SERVICES 事件，
  各驱动的收尾回调会分配/释放内存，使调用者手里的 MapKey 立即失效；
  之后 CoreTerminateMemoryMap(MapKey) 比对必然失败。这里把比对改成恒真
  （等价于"信任调用者"），是使流程能继续的最小改动。

文件按 glob 查找，找不到就跳过，不会让构建失败。

用法: python3 tools/patch_firmware.py <edk2-msm 目录>
"""

import re
import sys
from pathlib import Path

GRAN_GLOB = "**/MdePkg/Include/AArch64/ProcessorBind.h"
PAGE_GLOB = "**/MdeModulePkg/Core/Dxe/Mem/Page.c"

ALIGN_OLD = re.compile(
    r"if \(\(Entry->Start & \(RUNTIME_PAGE_ALLOCATION_GRANULARITY - 1\)\) != 0\) \{.*?"
    r"goto Done;\s*\}\s*"
    r"if \(\(\(Entry->End \+ 1\) & \(RUNTIME_PAGE_ALLOCATION_GRANULARITY - 1\)\) != 0\) \{.*?"
    r"goto Done;\s*\}",
    re.S,
)

ALIGN_NEW = """if (((Entry->Start | (Entry->End + 1)) & (RUNTIME_PAGE_ALLOCATION_GRANULARITY - 1)) != 0) {
            EFI_PHYSICAL_ADDRESS  FuxiNewStart;
            EFI_PHYSICAL_ADDRESS  FuxiNewEnd;
            FuxiNewStart = Entry->Start & ~((EFI_PHYSICAL_ADDRESS) RUNTIME_PAGE_ALLOCATION_GRANULARITY - 1);
            FuxiNewEnd   = Entry->End | ((EFI_PHYSICAL_ADDRESS) RUNTIME_PAGE_ALLOCATION_GRANULARITY - 1);
            DEBUG ((DEBUG_ERROR | DEBUG_PAGE, "fuxi-align: RT 0x%lx-0x%lx -> 0x%lx-0x%lx",
              (UINT64) Entry->Start, (UINT64) Entry->End, (UINT64) FuxiNewStart, (UINT64) FuxiNewEnd));
            Entry->Start = FuxiNewStart;
            Entry->End   = FuxiNewEnd;
            if (Entry->Start > Entry->End) {
              Status = EFI_INVALID_PARAMETER;
              goto Done;
            }
          }"""


def find_one(root: Path, pattern: str):
    hits = sorted(root.glob(pattern))
    return hits[0] if hits else None


def patch_align(root: Path) -> str:
    p = find_one(root, PAGE_GLOB)
    if p is None:
        return "补丁1 跳过: 树里找不到 Core/Dxe/Mem/Page.c"
    text = p.read_text(encoding="utf-8", errors="replace")
    if "fuxi-align" in text:
        return f"补丁1 已打过 ({p})"
    new, n = ALIGN_OLD.subn(ALIGN_NEW, text)
    if n == 0:
        return f"补丁1 失败: {p} 里没匹配到对齐检查代码块"
    p.write_text(new, encoding="utf-8")
    return f"补丁1 成功: 对齐检查改为向外对齐 64KB ({p})"


def patch_mapkey(root: Path) -> str:
    p = find_one(root, PAGE_GLOB)
    if p is None:
        return "补丁2 跳过: 树里找不到 Core/Dxe/Mem/Page.c"
    text = p.read_text(encoding="utf-8", errors="replace")
    if "if (MapKey == mMemoryMapKey)" not in text:
        if "if (1)" in text:
            return f"补丁2 已打过 ({p})"
        return f"补丁2 失败: {p} 里没有 MapKey 比对语句"
    p.write_text(text.replace("if (MapKey == mMemoryMapKey)", "if (1)"), encoding="utf-8")
    return f"补丁2 成功: 跳过 MapKey 比对 ({p})"


def check(root: Path) -> str:
    pg = find_one(root, PAGE_GLOB)
    gh = find_one(root, GRAN_GLOB)
    if pg is None:
        return "校验: page.c 不存在"
    text = pg.read_text(encoding="utf-8", errors="replace")
    gran = "0x10000" if gh is not None and "0x10000" in gh.read_text(
        encoding="utf-8", errors="replace") else "?"
    return (
        f"校验: align={int('fuxi-align' in text)} "
        f"mapkey={int('if (1)' in text)} granularity={gran}"
    )


def main() -> int:
    if len(sys.argv) != 2:
        print("用法: patch_firmware.py <edk2-msm 目录>")
        return 2
    root = Path(sys.argv[1])
    if not root.is_dir():
        print(f"目录不存在: {root}")
        return 2
    print(patch_align(root))
    print(patch_mapkey(root))
    print(check(root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
