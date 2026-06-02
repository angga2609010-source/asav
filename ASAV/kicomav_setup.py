"""Configure KicomAV rules path and download signatures."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from asav.config import APP_DIR

RULES_DIR = APP_DIR / "signatures"
USER_RULES_DIR = APP_DIR / "user_rules"
KICOMAV_ENV = Path.home() / ".kicomav" / ".env"


def configure_kicomav_environment() -> Path:
    """Ensure KicomAV env vars and ~/.kicomav/.env exist."""
    RULES_DIR.mkdir(parents=True, exist_ok=True)
    USER_RULES_DIR.mkdir(parents=True, exist_ok=True)
    KICOMAV_ENV.parent.mkdir(parents=True, exist_ok=True)

    system = str(RULES_DIR.resolve())
    user = str(USER_RULES_DIR.resolve())

    os.environ["SYSTEM_RULES_BASE"] = system
    os.environ["USER_RULES_BASE"] = user
    os.environ["KICOMAV_SUPPRESS_WARNINGS"] = "1"

    content = (
        f"SYSTEM_RULES_BASE={system}\n"
        f"USER_RULES_BASE={user}\n"
        f"KICOMAV_SUPPRESS_WARNINGS=1\n"
    )
    if not KICOMAV_ENV.exists() or KICOMAV_ENV.read_text(encoding="utf-8") != content:
        KICOMAV_ENV.write_text(content, encoding="utf-8")

    return RULES_DIR


def bootstrap_signatures() -> tuple[bool, str]:
    """Download malware signatures if possible."""
    configure_kicomav_environment()
    try:
        import kicomav

        result = kicomav.update()
        count = len(result.updated_files or [])
        if result.errors:
            return False, "; ".join(result.errors[:3])
        if count:
            return True, f"Downloaded {count} signature file(s)."
        if any(RULES_DIR.rglob("*.yar")) or any(RULES_DIR.rglob("*.yara")):
            return True, "Signatures already present."
        return True, "Signature server reachable; no new files."
    except Exception as exc:
        return False, str(exc)
