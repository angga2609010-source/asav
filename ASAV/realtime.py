"""Real-time file system monitoring with KicomAV."""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional, Set

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from asav import quarantine as quarantine_mod
from asav.config import AppConfig
from asav.engine import ScanEngine
from asav.paths import quick_scan_paths
from asav.scanning import is_archive_path

logger = logging.getLogger(__name__)

ThreatHandler = Callable[[str, str], None]

# Wait for downloads / extractions to finish writing
STABLE_CHECKS = 4
STABLE_INTERVAL_SEC = 0.5
RETRY_DELAYS_SEC = (0.0, 1.5, 4.0, 8.0)


class _RealtimeHandler(FileSystemEventHandler):
    def __init__(
        self,
        engine: ScanEngine,
        cfg: AppConfig,
        on_threat: Optional[ThreatHandler],
    ) -> None:
        super().__init__()
        self._engine = engine
        self._cfg = cfg
        self._on_threat = on_threat
        self._pending: Set[str] = set()
        self._lock = threading.Lock()

    def _wait_until_stable(self, path: str, timeout_sec: float = 20.0) -> bool:
        deadline = time.time() + timeout_sec
        last_size = -1
        stable = 0
        while time.time() < deadline:
            try:
                size = os.path.getsize(path)
            except OSError:
                time.sleep(STABLE_INTERVAL_SEC)
                continue
            if size == last_size:
                stable += 1
                if stable >= STABLE_CHECKS:
                    return True
            else:
                stable = 0
                last_size = size
            time.sleep(STABLE_INTERVAL_SEC)
        return False

    def _schedule_scan(self, path: str) -> None:
        p = Path(path)
        if not p.is_file():
            return
        if quarantine_mod.is_quarantined_path(path):
            return
        with self._lock:
            if path in self._pending:
                return
            self._pending.add(path)

        def run() -> None:
            try:
                archive = is_archive_path(path)
                base_delay = 2.0 if archive else 0.5
                time.sleep(base_delay)

                if not Path(path).is_file():
                    return
                if not self._wait_until_stable(path, timeout_sec=30.0 if archive else 15.0):
                    logger.debug("File never stabilized for realtime scan: %s", path)

                for delay in RETRY_DELAYS_SEC:
                    if delay:
                        time.sleep(delay)
                    if not Path(path).is_file():
                        return
                    try:
                        result = self._engine.scan_path_sync(
                            path,
                            scan_archives=self._cfg.scan_archives,
                        )
                    except Exception:
                        logger.exception("Realtime scan failed: %s", path)
                        continue

                    if result.infected:
                        name = result.malware_name or "Unknown"
                        if self._cfg.auto_quarantine:
                            quarantine_mod.quarantine_file(path, name)
                        if self._on_threat:
                            self._on_threat(path, name)
                        return
            finally:
                with self._lock:
                    self._pending.discard(path)

        threading.Thread(target=run, daemon=True, name="asav-rt-scan").start()

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._schedule_scan(event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._schedule_scan(event.src_path)


class RealtimeGuard:
    def __init__(self, engine: ScanEngine, cfg: AppConfig) -> None:
        self._engine = engine
        self._cfg = cfg
        self._observer: Optional[Observer] = None
        self._on_threat: Optional[ThreatHandler] = None

    @property
    def active(self) -> bool:
        return self._observer is not None and self._observer.is_alive()

    def _watch_paths(self) -> List[str]:
        if self._cfg.realtime_paths:
            return [p for p in self._cfg.realtime_paths if Path(p).exists()]
        return quick_scan_paths()

    def start(self, on_threat: Optional[ThreatHandler] = None) -> bool:
        if self.active:
            return True
        paths = self._watch_paths()
        if not paths:
            return False
        self._on_threat = on_threat
        handler = _RealtimeHandler(self._engine, self._cfg, on_threat)
        self._observer = Observer()
        for path in paths:
            try:
                self._observer.schedule(handler, path, recursive=True)
            except OSError as exc:
                logger.warning("Cannot watch %s: %s", path, exc)
        self._observer.start()
        return self._observer.is_alive()

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
