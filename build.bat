@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ASAV_SETUP="
if /i "%~1"=="setup" set "ASAV_SETUP=1"
if /i "%~1"=="/setup" set "ASAV_SETUP=1"

echo ============================================
echo  ASAV - Build Windows executable
echo ============================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Run install.bat or setup.bat first.
  if defined ASAV_SETUP exit /b 1
  pause
  exit /b 1
)

echo Installing build tools...
".venv\Scripts\python.exe" -m pip install -q pyinstaller>=6.0
if errorlevel 1 goto build_fail

echo.
echo Building ASAV.exe - this may take several minutes...
if defined ASAV_SETUP (
  ".venv\Scripts\python.exe" -m PyInstaller --noconfirm asav.spec
) else (
  ".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean asav.spec
)

if errorlevel 1 goto build_fail

if not exist "dist\ASAV\ASAV.exe" (
  echo [ERROR] Build finished but dist\ASAV\ASAV.exe was not created.
  goto build_fail
)

echo.
echo ============================================
echo  Build complete.
echo  Run: dist\ASAV\ASAV.exe
echo  Copy the whole dist\ASAV folder to install elsewhere.
echo ============================================
echo.
if defined ASAV_SETUP exit /b 0
pause
exit /b 0

:build_fail
echo.
echo [ERROR] Build failed. See messages above.
if defined ASAV_SETUP exit /b 1
pause
exit /b 1
