@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] ASAV is not installed yet.
  echo Run install.bat first - do not use plain pip install.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" main.py
if errorlevel 1 (
  echo.
  echo ASAV exited with an error.
  echo If missing modules, run install.bat again.
)
pause
exit /b 0