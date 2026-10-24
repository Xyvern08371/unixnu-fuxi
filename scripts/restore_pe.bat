@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

rem ============================================================
rem  restore_pe.bat -- 把 fuxi 刷回 PixelOS
rem  依赖: E:\fuxi\boot.img  (PixelOS 的原始 boot, 已有)
rem        E:\fuxi\vbmeta.img
rem ============================================================

set "ADB=%~dp0adb-platform-tools-latest-windows\platform-tools\fastboot.exe"
set "DIR=E:\fuxi"

echo.
echo ============ fuxi 回滚到 PixelOS ============
echo.

if not exist "%ADB%" (
  echo [错误] 找不到 fastboot: %ADB%
  goto :end
)
if not exist "%DIR%\boot.img" (
  echo [错误] 找不到 %DIR%\boot.img
  goto :end
)

"%ADB%" devices
echo.

echo 将执行:
echo   fastboot flash boot "%DIR%\boot.img"
if exist "%DIR%\vbmeta.img" (
  echo   fastboot --disable-verity --disable-verification flash vbmeta "%DIR%\vbmeta.img"
)
echo.
set /p CONFIRM="确认回滚? 输入 YES 回车: "
if /i not "!CONFIRM!"=="YES" (
  echo 已取消。
  goto :end
)

echo.
echo 刷回 boot...
"%ADB%" flash boot "%DIR%\boot.img"
if errorlevel 1 (
  echo [失败] boot 刷回失败。尝试直接进 fastboot 重试:
  echo        adb reboot bootloader
  goto :end
)

if exist "%DIR%\vbmeta.img" (
  echo 处理 vbmeta...
  "%ADB%" --disable-verity --disable-verification flash vbmeta "%DIR%\vbmeta.img"
)

echo.
echo 完成, 重启...
"%ADB%" reboot

:end
echo.
pause
endlocal
