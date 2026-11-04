@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

rem ============================================================
rem  flash_latest.bat -- 一键: 找最新 zip -> 解压 -> 校验 -> 刷入 -> 重启
rem  用法: 双击即可。zip 放 E:\download\fuxi-uefi*.zip
rem ============================================================

set "TOOLS=%~dp0adb-platform-tools-latest-windows\platform-tools"
set "FB=%TOOLS%\fastboot.exe"
set "DL=E:\download"
set "TMPD=E:\fuxi\_unpack"

echo.
echo ===== 一键刷入最新固件 =====
echo.

if not exist "%FB%" (
  echo [错误] 找不到 fastboot: %FB%
  goto :end
)

rem --- 找最新 zip ---
set "ZIP="
for /f "delims=" %%f in ('dir /b /o-d "%DL%\fuxi-uefi*.zip" 2^>nul') do (
  if not defined ZIP set "ZIP=%DL%\%%f"
)
if not defined ZIP (
  echo [错误] %DL% 下没有 fuxi-uefi*.zip
  goto :end
)
echo 使用: !ZIP!

rem --- 解压 ---
if exist "%TMPD%" rd /s /q "%TMPD%"
mkdir "%TMPD%" 2>nul
powershell -NoProfile -Command "Expand-Archive -LiteralPath '!ZIP!' -DestinationPath '%TMPD%' -Force" || goto :fail

set "IMG="
for /r "%TMPD%" %%f in (boot-fuxi.img) do if not defined IMG set "IMG=%%f"
if not defined IMG (
  echo [错误] 压缩包里没有 boot-fuxi.img
  goto :fail
)
for %%f in ("!IMG!") do echo 镜像: %%~nxf  %%~zf 字节

rem --- 设备 ---
"%FB%" devices
echo.
echo 确认手机在 fastboot 模式（长按电源15秒关机，再按住电源+音量下）
set /p OK="回车继续，输入 n 取消: "
if /i "!OK!"=="n" goto :end

echo.
"%FB%" flash boot "!IMG!"
if errorlevel 1 goto :fail

echo.
"%FB%" reboot
echo.
echo 刷入完成，看屏幕。
goto :end

:fail
echo.
echo [失败] 见上面的报错

:end
if exist "%TMPD%" rd /s /q "%TMPD%" 2>nul
echo.
pause
endlocal
