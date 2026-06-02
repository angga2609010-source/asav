@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ASAV_NO_PAUSE="
if /i "%~1"=="nopause" set "ASAV_NO_PAUSE=1"

echo ============================================
echo  ASAV - Create single-file installer
echo ============================================
echo.
echo Output: release\ASAV-Setup.exe
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\build_setup_exe.ps1" -Root "%~dp0."
if errorlevel 1 goto build_fail

if not exist "%~dp0release\ASAV-Setup.exe" goto build_fail

echo.
echo ============================================
echo  Give users: release\ASAV-Setup.exe
echo ============================================
echo.
if not defined ASAV_NO_PAUSE pause
exit /b 0

:build_fail
echo.
echo [ERROR] Could not build ASAV-Setup.exe
echo.
if not defined ASAV_NO_PAUSE pause
exit /b 1
