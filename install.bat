@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ASAV_SETUP="
if /i "%~1"=="setup" set "ASAV_SETUP=1"
if /i "%~1"=="/setup" set "ASAV_SETUP=1"

echo ============================================
echo  ASAV Installer
echo ============================================
echo.
echo This script installs Python 3.12 if needed, then
echo KicomAV and all ASAV dependencies into .venv
echo.

call :pick_python
if not defined PYVER call :install_python
if not defined PYVER call :pick_python
if not defined PYVER goto no_python

echo Using Python %PYVER% for this project.
echo All packages go into: %~dp0.venv
echo Do NOT use plain "pip install" - it may target Python 3.14.
echo.

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  call :create_venv
  if errorlevel 1 goto venv_fail
)

echo Upgrading pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip wheel setuptools
if errorlevel 1 goto pip_fail

echo Installing ASAV dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto deps_fail

echo.
echo Verifying install...
".venv\Scripts\python.exe" -c "import customtkinter, kicomav; print('OK - kicomav', kicomav.__version__)"
if errorlevel 1 goto verify_fail

echo Downloading malware signatures...
".venv\Scripts\python.exe" -c "from asav.kicomav_setup import bootstrap_signatures; ok, msg = bootstrap_signatures(); print(msg); raise SystemExit(0 if ok else 1)"
if errorlevel 1 echo Warning: signature download had issues - use Update signatures in the app.

echo.
echo ============================================
echo  Installation complete.
echo  Run: run_asav.bat
echo  Build exe: build.bat
echo ============================================
echo.
if defined ASAV_SETUP exit /b 0
pause
exit /b 0

REM --- Find Python 3.10 - 3.13 via py launcher ---
:pick_python
set "PYVER="
where py >nul 2>nul
if errorlevel 1 goto pick_python_direct
call :tryver 3.12
if defined PYVER exit /b 0
call :tryver 3.13
if defined PYVER exit /b 0
call :tryver 3.11
if defined PYVER exit /b 0
call :tryver 3.10
exit /b 0

:pick_python_direct
call :try_direct 3.12
if defined PYVER exit /b 0
call :try_direct 3.13
if defined PYVER exit /b 0
call :try_direct 3.11
if defined PYVER exit /b 0
call :try_direct 3.10
exit /b 0

:tryver
py -%~1 -V >nul 2>&1
if not errorlevel 1 set "PYVER=%~1"
exit /b 0

:try_direct
set "TRYDIR=%LOCALAPPDATA%\Programs\Python\Python%~1"
if exist "%TRYDIR%\python.exe" (
  set "PATH=%TRYDIR%;%TRYDIR%\Scripts;%PATH%"
  set "PYVER=%~1"
)
exit /b 0

REM --- Install Python 3.12 when missing ---
:install_python
echo.
echo --------------------------------------------
echo  Python 3.10-3.13 not found
echo  Installing Python 3.12 for ASAV...
echo --------------------------------------------
echo.

call :install_python_winget
call :pick_python
if defined PYVER exit /b 0

call :install_python_py
call :pick_python
if defined PYVER exit /b 0

call :install_python_download
call :pick_python
exit /b 0

:install_python_winget
where winget >nul 2>nul
if errorlevel 1 exit /b 0
echo Trying Microsoft winget...
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements --disable-interactivity
call :refresh_python_path
exit /b 0

:install_python_py
where py >nul 2>nul
if errorlevel 1 exit /b 0
echo Trying Python launcher: py install 3.12
py install 3.12
if errorlevel 1 exit /b 0
echo Waiting for install to finish...
timeout /t 5 /nobreak >nul
call :refresh_python_path
exit /b 0

:install_python_download
echo Downloading Python 3.12.10 installer...
set "PYINSTALLER=%TEMP%\asav-python312-install.exe"
set "PYURL=https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"

powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PYURL%' -OutFile '%PYINSTALLER%' -UseBasicParsing"
if not exist "%PYINSTALLER%" exit /b 0

echo Running silent installer - may take a minute...
"%PYINSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=1
del "%PYINSTALLER%" 2>nul
call :refresh_python_path
exit /b 0

:refresh_python_path
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
  set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"
)
exit /b 0

:create_venv
where py >nul 2>nul
if not errorlevel 1 (
  py -%PYVER% -m venv .venv
  exit /b %ERRORLEVEL%
)
set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python%PYVER%\python.exe"
if exist "%PYEXE%" (
  "%PYEXE%" -m venv .venv
  exit /b %ERRORLEVEL%
)
exit /b 1

:no_python
echo [ERROR] Could not find or install a compatible Python.
echo.
echo ASAV needs Python 3.10, 3.11, 3.12, or 3.13 - not 3.14.
echo Python 3.14 cannot install the yara-python engine wheel on Windows.
echo.
echo Try manually, then run install.bat again:
echo   winget install Python.Python.3.12
echo   py install 3.12
echo.
echo Or download: https://www.python.org/downloads/release/python-31210/
echo Enable "Add python.exe to PATH" during setup.
echo.
if defined ASAV_SETUP exit /b 1
pause
exit /b 1

:venv_fail
echo [ERROR] Could not create .venv
if defined ASAV_SETUP exit /b 1
pause
exit /b 1

:pip_fail
echo [ERROR] pip upgrade failed
if defined ASAV_SETUP exit /b 1
pause
exit /b 1

:deps_fail
echo [ERROR] Could not install requirements.txt
echo.
echo If you see yara-python errors, you used the wrong Python.
echo Always run install.bat - do not run "pip install" alone.
echo.
if defined ASAV_SETUP exit /b 1
pause
exit /b 1

:verify_fail
echo [ERROR] Packages installed but import failed.
if defined ASAV_SETUP exit /b 1
pause
exit /b 1
