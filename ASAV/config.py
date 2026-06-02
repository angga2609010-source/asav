"""Persistent application settings."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List

APP_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "ASAV"
QUARANTINE_DIR = APP_DIR / "quarantine"
CONFIG_PATH = APP_DIR / "config.json"


@dataclass
class AppConfig:
    realtime_enabled: bool = False
    scan_archives: bool = True
    auto_quarantine: bool = True
    run_at_startup: bool = False
    start_in_tray: bool = True
    minimize_to_tray: bool = True
    exclusions: List[str] = field(default_factory=list)
    realtime_paths: List[str] = field(default_factory=list)

    def ensure_dirs(self) -> None:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> AppConfig:
    cfg = AppConfig()
    cfg.ensure_dirs()
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            cfg.realtime_enabled = bool(data.get("realtime_enabled", cfg.realtime_enabled))
            cfg.scan_archives = bool(data.get("scan_archives", cfg.scan_archives))
            cfg.auto_quarantine = bool(data.get("auto_quarantine", cfg.auto_quarantine))
            cfg.run_at_startup = bool(data.get("run_at_startup", cfg.run_at_startup))
            cfg.start_in_tray = bool(data.get("start_in_tray", cfg.start_in_tray))
            cfg.minimize_to_tray = bool(data.get("minimize_to_tray", cfg.minimize_to_tray))
            cfg.exclusions = list(data.get("exclusions", []))
            cfg.realtime_paths = list(data.get("realtime_paths", []))
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def save_config(cfg: AppConfig) -> None:
    cfg.ensure_dirs()
    CONFIG_PATH.write_text(
        json.dumps(asdict(cfg), indent=2),
        encoding="utf-8",
    )
