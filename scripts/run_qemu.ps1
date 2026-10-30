# 运行 FuxiLoader.efi 的 QEMU 自检
#
# 用途: 在没有 Renegade UEFI 镜像的情况下, 先用 PC 上的 aarch64 UEFI 模拟器
#       验证引导器逻辑: CurrentEL、文件读取、ExitBootServices。
#
# 前置:
#   1. 装 QEMU for Windows (https://qemu.weilnetz.de/w64/ , 约 120MB, 默认路径)
#   2. E:\qemu-share 里有 FuxiLoader.efi / fuxi.dtb / startup.nsh
#
# 用法:
#   powershell -ExecutionPolicy Bypass -File run_qemu.ps1
#   退出: 在 QEMU 窗口按 Ctrl+A 然后 X; 或直接关窗口

param(
  [string]$QemuExe = "",
  [string]$Share   = "E:\qemu-share",
  [int]$MemMB      = 2048
)

$ErrorActionPreference = "Stop"

function Find-Qemu {
  if ($QemuExe -and (Test-Path $QemuExe)) { return $QemuExe }
  $cands = @(
    "C:\Program Files\qemu\qemu-system-aarch64.exe",
    "C:\Program Files (x86)\qemu\qemu-system-aarch64.exe",
    "D:\Program Files\qemu\qemu-system-aarch64.exe",
    "E:\Program Files\qemu\qemu-system-aarch64.exe",
    "C:\msys64\mingw64\bin\qemu-system-aarch64.exe",
    "C:\msys64\ucrt64\bin\qemu-system-aarch64.exe",
    "D:\msys64\mingw64\bin\qemu-system-aarch64.exe",
    "D:\qemu\ucrt64\bin\qemu-system-aarch64.exe",
    "D:\qemu\mingw64\bin\qemu-system-aarch64.exe"
  )
  foreach ($c in $cands) { if (Test-Path $c) { return $c } }
  $cmd = Get-Command qemu-system-aarch64.exe -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  return $null
}

function Find-Firmware($qemuExe) {
  # 1) 周围目录里的 QEMU_EFI.fd (Linaro/上流传的那种)
  foreach ($p in @("$Share\QEMU_EFI.fd", "$PSScriptRoot\QEMU_EFI.fd")) {
    if (Test-Path $p) { return $p }
  }
  # 2) QEMU 自带 share\edk2-aarch64-code.fd
  $qdir = Split-Path $qemuExe -Parent
  foreach ($p in @("$qdir\share\edk2-aarch64-code.fd", "$qdir\..\share\edk2-aarch64-code.fd")) {
    if (Test-Path $p) { return (Resolve-Path $p).Path }
  }
  return $null
}

Write-Host "=== FuxiLoader / QEMU aarch64 自检 ===" -ForegroundColor Cyan

$qemu = Find-Qemu
if (-not $qemu) {
  Write-Host "[错误] 没找到 qemu-system-aarch64.exe" -ForegroundColor Red
  Write-Host "       去 https://qemu.weilnetz.de/w64/ 下最新的 w64 安装包, 默认路径安装"
  exit 1
}
Write-Host "QEMU    : $qemu"

$fw = Find-Firmware $qemu
if (-not $fw) {
  Write-Host "[错误] 没找到 aarch64 UEFI 固件" -ForegroundColor Red
  Write-Host "       把 QEMU_EFI.fd 放到 $Share, 或确认 QEMU 的 share\edk2-aarch64-code.fd 存在"
  exit 1
}
Write-Host "固件    : $fw"

foreach ($f in @("FuxiLoader.efi", "startup.nsh")) {
  if (-not (Test-Path (Join-Path $Share $f))) {
    Write-Host "[错误] $Share 里缺 $f" -ForegroundColor Red
    exit 1
  }
}
Write-Host "共享目录: $Share"
Write-Host ""
Write-Host "启动 QEMU（窗口里应该会看到 FuxiLoader 的打印）..." -ForegroundColor Yellow
Write-Host "退出方法: Ctrl+A 然后按 X" -ForegroundColor DarkGray
Write-Host ""

# virt + virtio-blk 挂载共享目录; vvfat 让 UEFI 直接看到 FAT 卷
& $qemu `
  -M virt -cpu cortex-a72 -m $MemMB -smp 2 `
  -nographic -no-reboot `
  -bios $fw `
  -drive if=none,format=raw,file=fat:rw:$Share,id=hd0 `
  -device virtio-blk-device,drive=hd0 `
  -net none

Write-Host ""
Write-Host "QEMU 已退出。" -ForegroundColor Cyan
