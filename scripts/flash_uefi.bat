@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

rem ============================================================
rem  flash_uefi.bat -- 把 UEFI 镜像刷进 fuxi 的 boot 分区
rem  用法: 把 uefi 镜像放到 E:\fuxi\ 然后双击本文件
rem  回滚: 跑 restore_pe.bat
rem ============================================================

set "ADB=%~dp0adb-platform-tools-latest-windows\platform-tools\fastboot.exe"
set "DIR=E:\fuxi"

echo.
echo ============ fuxi UEFI 刷入工具 ============
echo.

if not exist "%ADB%" (
  echo [错误] 找不到 fastboot: %ADB%
  echo        请先解压 adb-platform-tools-latest-windows.zip 到本目录
  goto :end
)

echo 查找 %DIR% 下的 UEFI 镜像...
set "IMG="
for %%f in ("%DIR%\*uefi*.img" "%DIR%\*fuxi*.img") do (
  if exist "%%~f" if not defined IMG set "IMG=%%~f"
)

if not defined IMG (
  echo [错误] 没找到镜像。需要 E:\fuxi 下有名字含 uefi 或 fuxi 的 .img 文件
  echo        当前目录内容:
  dir /b "%DIR%\*.img" 2>nul
  goto :end
)

echo 找到镜像: !IMG!
for %%f in ("!IMG!") do echo 大小: %%~zf 字节

echo.
echo 检查设备...
"%ADB%" devices
echo.

echo ===== 即将执行 =====
echo   fastboot flash boot "!IMG!"
echo.
echo 风险提示:
echo   - 刷完后开机是 UEFI 控制台, 安卓暂时进不去
echo   - 要回安卓: 跑 restore_pe.bat (刷回 PixelOS 的 boot.img)
echo   - 万一完全黑屏: 长按电源 10 秒强制重启, 仍不行走 9008
echo.
set /p CONFIRM="确认继续? 输入 YES 回车: "
if /i not "!CONFIRM!"=="YES" (
  echo 已取消。
  goto :end
)

echo.
echo 刷入中...
"%ADB%" flash boot "!IMG!"
if errorlevel 1 (
  echo.
  echo [失败] 刷入报错。设备仍可用, 跑 restore_pe.bat 回滚。
  goto :end
)

echo.
echo 刷入完成。重启:
"%ADB%" reboot

:end
echo.
pause
endlocal
