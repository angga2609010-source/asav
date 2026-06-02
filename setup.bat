@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================
echo  ASAV - Full setup
echo ============================================
echo.
echo Step 1: Python and scanning engine
echo Step 2: Build application
echo Step 3: Launch ASAV
echo.

call "%~dp0install.bat" setup
if errorlevel 1 goto setup_fail

if not exist "%~dp0dist\ASAV\ASAV.exe" (
  echo.
  echo Building ASAV.exe - first run may take a few minutes...
  echo.
  call "%~dp0build.bat" setup
  if errorlevel 1 goto setup_fail
)

if not exist "%~dp0dist\ASAV\ASAV.exe" (
  echo [ERROR] ASAV.exe was not created.
  goto setup_fail
)

call :create_desktop_shortcut

echo.
echo ============================================
echo  Setup complete - starting ASAV
echo ============================================
echo.

start "" "%~dp0dist\ASAV\ASAV.exe"
exit /b 0

:create_desktop_shortcut
set "LNK=%USERPROFILE%\Desktop\ASAV.lnk"
set "TARGET=%~dp0dist\ASAV\ASAV.exe"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s = New-Object -ComObject WScript.Shell; $l = $s.CreateShortcut('%LNK%'); $l.TargetPath = '%TARGET%'; $l.WorkingDirectory = '%~dp0dist\ASAV'; $l.Description = 'ASAV KicomAV Protection'; $l.Save()" >nul 2>&1
exit /b 0

:setup_fail
echo.
echo [ERROR] ASAV setup did not finish.
echo.
pause
exit /b 1
