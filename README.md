# ASAV (Python GUI + KicomAV engine)



ASAV (AnggaSabber's AntiVirus) is a lightweight antivirus solution written in
        <strong>Python</strong>. It combines speed, simplicity, and effective malware
        detection using the open-source
        <a href="https://github.com/hanul93/kicomav" target="_blank">
            KicomAV Engine

## Features

- KicomAV scanning engine integration (`kicomav.Scanner`)
- Quick scan, full scan, and custom path scan
- Real-time file protection using filesystem monitoring
- Threat quarantine with restore/delete actions
- Signature update action from the UI
- Persistent settings (exclusions, real-time toggle, quarantine behavior)

## Project structure

- `main.py` — app entry point
- `gui/app.py` — CustomTkinter UI
- `asav/engine.py` — KicomAV scan wrapper + threaded jobs
- `asav/realtime.py` — watchdog-based real-time monitor
- `asav/quarantine.py` — quarantine index + file actions
- `asav/config.py` — persistent config in `%LOCALAPPDATA%\\ASAV`

## Requirements

- Windows 10/11
- **Python 3.10, 3.11, 3.12, or 3.13** (not 3.14)
- Internet connection for first install / signature updates

### Why not Python 3.14?

KicomAV depends on `yara-python`. On Windows, pip can only install it easily when a pre-built wheel exists. Wheels exist for Python 3.10–3.13, but **not 3.14**, so pip tries to compile from source and fails with errors about `wheel` and **Microsoft Visual C++ 14.0**.

## Installation

### If you only have Python 3.14 (common fix)

Open **Command Prompt** and run:

```bat
py install 3.12
```

Close the terminal, open a new one, then run `install.bat` in this folder.

Or download Python 3.12 from:
https://www.python.org/downloads/release/python-31210/

### One-click setup (recommended)

Double-click or run:

```bat
setup.bat
```

This installs **Python 3.12** (if needed), KicomAV and dependencies, builds `ASAV.exe`, adds a desktop shortcut, and **starts ASAV**.

### Normal install (developers)

```bat
install.bat
run_asav.bat
```

`install.bat` installs Python and packages only (no exe build, no auto-launch).

### Single-file installer for other PCs

On your build machine, after the project is ready:

```bat
make_installer.bat
```

Share **`release\ASAV-Setup.exe`** with others. On a new PC they run that one file; it extracts the project, runs full setup, and opens ASAV.

**Important:** Do not run plain `pip install -r requirements.txt` — on your PC that often targets **Python 3.14** and fails on `yara-python`. Always use `install.bat`, which creates a `.venv` folder with the correct Python.

Manual install (only if you know which Python to use):

```bat
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Run

```bat
run_asav.bat
```

Or:

```bat
python main.py
```

## Build Windows executable

After `install.bat`:

```bat
build.bat
```

Output folder (copy the whole folder to install elsewhere):

`dist\ASAV\ASAV.exe`

Settings, quarantine, and signatures still use `%LOCALAPPDATA%\ASAV`. Windows startup (Settings) registers `ASAV.exe` with `--tray` when you enable run at startup.

## Notes

- Quarantined files and settings are saved in:
  `%LOCALAPPDATA%\\ASAV`
- Real-time protection monitors common user directories by default (Downloads, Desktop, Documents, temp paths).
- This project is a local antivirus front-end powered by KicomAV signatures and detection logic.
