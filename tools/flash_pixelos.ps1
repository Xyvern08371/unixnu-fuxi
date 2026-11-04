# 按 fastboot-info.txt 完整刷写 PixelOS
# 用法：手机进 fastboot，然后在 PowerShell 里执行本脚本
$ErrorActionPreference = "Stop"
$tmp = "E:\ios-on-fuxi\scripts\_tmp"; $env:TEMP = $tmp; $env:TMP = $tmp

$FB  = "E:\ios-on-fuxi\scripts\adb-platform-tools-latest-windows\platform-tools\fastboot.exe"
$DIR = "E:\download\pixelos-fuxi"

function Say($s) { Write-Host "`n=== $s ===" -ForegroundColor Cyan }
function FB() {
    Write-Host "  > fastboot $args" -ForegroundColor Gray
    & $FB @args 2>&1 | ForEach-Object { "    $_" }
}

Say "设备状态"
& $FB devices

Say "0) 切到 fastbootd（update-super 必须在这里跑）"
& $FB reboot fastboot 2>&1 | ForEach-Object { "  $_" }
Start-Sleep -Seconds 12
& $FB devices 2>&1 | ForEach-Object { "  $_" }

Say "1) boot 相关分区"
foreach ($p in @("boot","init_boot","dtbo","recovery","vendor_boot")) {
    $img = Join-Path $DIR "$p.img"
    if (Test-Path $img) {
        Write-Host "  --- $p ---" -ForegroundColor Yellow
        & $FB flash $p $img 2>&1 | ForEach-Object { "    $_" }
    } else { Write-Host "  缺 $p.img" -ForegroundColor Red }
}

Say "2) vbmeta（--apply-vbmeta 是关键，手刷最容易漏）"
& $FB flash --apply-vbmeta vbmeta (Join-Path $DIR "vbmeta.img") 2>&1 | ForEach-Object { "    $_" }
& $FB flash vbmeta_system (Join-Path $DIR "vbmeta_system.img") 2>&1 | ForEach-Object { "    $_" }

Say "3) 回到 bootloader 再进 fastbootd，执行 update-super"
& $FB reboot fastboot 2>&1 | ForEach-Object { "  $_" }
Start-Sleep -Seconds 12

Say "4) 动态分区（super 里的逻辑分区）"
foreach ($p in @("product","system","system_ext","system_dlkm","odm","vendor","vendor_dlkm")) {
    $img = Join-Path $DIR "$p.img"
    if (Test-Path $img) {
        Write-Host "  --- $p ---" -ForegroundColor Yellow
        & $FB flash $p $img 2>&1 | ForEach-Object { "    $_" }
    }
}

Say "5) 清 data / metadata"
& $FB erase userdata 2>&1 | ForEach-Object { "    $_" }
& $FB erase metadata 2>&1 | ForEach-Object { "    $_" }

Say "6) 重启"
& $FB reboot 2>&1 | ForEach-Object { "  $_" }

Say "完成"
Write-Host "  如果还是开机一半重启，看 avb/vbmeta 相关输出" -ForegroundColor Yellow
