"""Windows scan target paths."""

from __future__ import annotations

import os
import string
from pathlib import Path
from typing import List

# Skip noisy / system folders during directory walks
SKIP_DIR_NAMES = frozenset(
    {
        "$Recycle.Bin",
        "System Volume Information",
        "Windows.old",
        "Recovery",
        "Config.Msi",
        "node_modules",
        ".git",
        "__pycache__",
        "AppData",  # skip nested AppData when walking from profile root
    }
)


def _exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def quick_scan_paths() -> List[str]:
    """High-risk user folders only (fast, practical quick scan)."""
    home = Path.home()
    candidates = [
        home / "Downloads",
        home / "Desktop",
        home / "Documents",
        Path(os.environ.get("TEMP", "")),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Temp",
    ]
    seen: set[str] = set()
    paths: List[str] = []
    for p in candidates:
        if not p or not str(p).strip():
            continue
        if not _exists(p):
            continue
        resolved = str(p.resolve())
        key = resolved.lower()
        if key not in seen:
            seen.add(key)
            paths.append(resolved)
    return paths


def full_scan_paths() -> List[str]:
    """All ready fixed drives on Windows."""
    paths: List[str] = []
    for letter in string.ascii_uppercase:
        root = f"{letter}:\\"
        if os.path.exists(root):
            try:
                if os.path.ismount(root) or letter == "C":
                    paths.append(root)
            except OSError:
                paths.append(root)
    if not paths:
        paths.append("C:\\")
    return paths
