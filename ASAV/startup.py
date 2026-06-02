"""Windows startup registration for ASAV."""

from __future__ import annotations

import sys
from pathlib import Path

from asav.frozen import app_executable, is_frozen

APP_NAME = "ASAV"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def project_root() -> Path:
    if is_frozen():
        return app_executable().parent
    return Path(__file__).resolve().parent.parent


def launch_command(start_in_tray: bool = True) -> str:
    """Build the command written to the Windows Run registry key."""
    tray_flag = " --tray" if start_in_tray else ""

    if is_frozen():
        return f'"{app_executable()}"{tray_flag}'

    root = project_root()
    main_py = root / "main.py"
    venv_pythonw = root / ".venv" / "Scripts" / "pythonw.exe"
    venv_python = root / ".venv" / "Scripts" / "python.exe"

    if venv_pythonw.exists():
        interpreter = venv_pythonw
    elif venv_python.exists():
        interpreter = venv_python
    else:
        interpreter = Path(sys.executable)

    return f'"{interpreter}" "{main_py}"{tray_flag}'


def is_startup_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return bool(value)
    except OSError:
        return False


def enable_startup(*, start_in_tray: bool = True) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        cmd = launch_command(start_in_tray=start_in_tray)
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            RUN_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
        return True
    except OSError:
        return False


def disable_startup() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            RUN_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, APP_NAME)
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


def sync_startup(enabled: bool, *, start_in_tray: bool = True) -> bool:
    if enabled:
        return enable_startup(start_in_tray=start_in_tray)
    return disable_startup()
