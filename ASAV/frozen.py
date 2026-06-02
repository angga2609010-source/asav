"""Helpers when ASAV is packaged as a Windows executable (PyInstaller)."""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_executable() -> Path:
    """Path to ASAV.exe (or python.exe in dev)."""
    return Path(sys.executable).resolve()


def install_directory() -> Path:
    """Folder containing the app (dist/ASAV when frozen)."""
    if is_frozen():
        return app_executable().parent
    return Path(__file__).resolve().parent.parent
