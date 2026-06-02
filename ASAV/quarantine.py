"""Quarantine storage for detected threats."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

from asav.config import QUARANTINE_DIR

META_FILE = QUARANTINE_DIR / "quarantine_index.json"


@dataclass
class QuarantineEntry:
    id: str
    original_path: str
    quarantine_path: str
    malware_name: str
    quarantined_at: float

    @property
    def quarantined_at_str(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.quarantined_at))


def _load_index() -> List[dict]:
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    if not META_FILE.exists():
        return []
    try:
        return json.loads(META_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_index(entries: List[dict]) -> None:
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    META_FILE.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def list_quarantined() -> List[QuarantineEntry]:
    return [QuarantineEntry(**e) for e in _load_index()]


def is_quarantined_path(path: str) -> bool:
    try:
        resolved = str(Path(path).resolve()).lower()
    except OSError:
        resolved = path.lower()
    qroot = str(QUARANTINE_DIR.resolve()).lower()
    return resolved.startswith(qroot)


def quarantine_file(original_path: str, malware_name: str) -> Optional[QuarantineEntry]:
    """Move a file into quarantine and record metadata."""
    src = Path(original_path)
    if not src.is_file():
        return None
    if is_quarantined_path(str(src)):
        return None

    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    entry_id = uuid.uuid4().hex[:12]
    digest = hashlib.sha256(str(src).encode("utf-8", errors="replace")).hexdigest()[:16]
    dest_name = f"{entry_id}_{digest}{src.suffix}"
    dest = QUARANTINE_DIR / dest_name

    try:
        shutil.move(str(src), str(dest))
    except OSError:
        try:
            shutil.copy2(str(src), str(dest))
            os.remove(str(src))
        except OSError:
            return None

    record = QuarantineEntry(
        id=entry_id,
        original_path=str(src),
        quarantine_path=str(dest),
        malware_name=malware_name or "Unknown",
        quarantined_at=time.time(),
    )
    entries = _load_index()
    entries.append(asdict(record))
    _save_index(entries)
    return record


def restore_entry(entry_id: str) -> bool:
    entries = _load_index()
    target = next((e for e in entries if e["id"] == entry_id), None)
    if not target:
        return False

    src = Path(target["quarantine_path"])
    dst = Path(target["original_path"])
    if not src.is_file():
        entries = [e for e in entries if e["id"] != entry_id]
        _save_index(entries)
        return False

    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        stem, suffix = dst.stem, dst.suffix
        dst = dst.with_name(f"{stem}_restored_{int(time.time())}{suffix}")

    try:
        shutil.move(str(src), str(dst))
    except OSError:
        return False

    entries = [e for e in entries if e["id"] != entry_id]
    _save_index(entries)
    return True


def delete_entry(entry_id: str) -> bool:
    entries = _load_index()
    target = next((e for e in entries if e["id"] == entry_id), None)
    if not target:
        return False

    qpath = Path(target["quarantine_path"])
    if qpath.is_file():
        try:
            os.remove(qpath)
        except OSError:
            return False

    entries = [e for e in entries if e["id"] != entry_id]
    _save_index(entries)
    return True
