# 一键恢复：Xiaomi 13 (fuxi) 上的 iOS 16.7.16
#
# 需先手动进 fastboot：关机后长按 电源 + 音量下 约 10 秒
# 用法： powershell -ExecutionPolicy Bypass -File .\restore-fuxi-ios.ps1

$ErrorActionPreference = "Stop"

$fb   = "E:\ios-on-fuxi\scripts\adb-platform-tools-latest-windows\platform-tools\fastboot.exe"
$root = "E:\wsl\ios16-root-v9.simg"                       # 根卷（带 /product ADT 配套的改动）
$boot = "E:\download\fuxi-loader-work\fuxi-final.img"     # loader：跳 probe + 显示带宽票 + 触控上电

foreach ($f in @($fb, $root, $boot)) {
    if (-not (Test-Path $f)) { throw "缺少文件: $f" }
}

Write-Host "=== 检查 fastboot ===" -ForegroundColor Cyan
$devs = & $fb devices 2>&1 | Out-String
if ($devs -notmatch "fastboot") { throw "设备不在 fastboot：关机后长按 电源 + 音量下 10 秒" }
$devs.Trim() -split "`n" | ForEach-Object { "  $_" }

Write-Host "`n=== 刷根卷到 userdata（约 4~5 分钟）===" -ForegroundColor Cyan
& $fb -S 512M flash userdata $root 2>&1 | Select-Object -Last 3 | ForEach-Object { "  $_" }

Write-Host "`n=== 刷 loader 到 boot_a / boot_b ===" -ForegroundColor Cyan
& $fb flash boot_a $boot 2>&1 | Select-Object -Last 1 | ForEach-Object { "  boot_a $_" }
& $fb flash boot_b $boot 2>&1 | Select-Object -Last 1 | ForEach-Object { "  boot_b $_" }

Write-Host "`n=== 重启 ===" -ForegroundColor Cyan
& $fb reboot 2>&1 | ForEach-Object { "  $_" }

Write-Host @"

完成。首次启动较慢（CPU 渲染 + 缓存重建），耐心等。
预期结果：苹果 logo + 进度条 -> 锁屏（可触摸）

排查用镜像（控制台开，能看到日志）：
  E:\download\fuxi-loader-work\fuxi-gpu2.img      控制台开 + 新 ZAP
  E:\download\fuxi-loader-work\fuxi-product-con.img  控制台开 + /product ADT
文档：E:\ios-on-fuxi\docs-fuxi-product-fix.md
"@ -ForegroundColor Green
