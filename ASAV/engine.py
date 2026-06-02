"""KicomAV scanning engine wrapper."""

from __future__ import annotations

import fnmatch
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Generator, List, Optional

logger = logging.getLogger(__name__)

from asav import quarantine as quarantine_mod
from asav.config import AppConfig
from asav.kicomav_setup import configure_kicomav_environment
from asav.paths import SKIP_DIR_NAMES
from asav.scanning import scan_path_comprehensive, timeout_for_path

configure_kicomav_environment()

import kicomav  # noqa: E402
from kicomav import ScanResult, Scanner  # noqa: E402

try:
    from kicomav.kavcore.k2config import suppress_warnings

    suppress_warnings(True)
except ImportError:
    pass

PhaseCallback = Callable[[str], None]
ProgressCallback = Callable[[str, int, int], None]
ThreatCallback = Callable[[ScanResult], None]
FinishedCallback = Callable[[dict], None]

MAX_SCAN_FILE_BYTES = 200 * 1024 * 1024


class ScanKind(str, Enum):
    QUICK = "quick"
    FULL = "full"
    CUSTOM = "custom"
    FILE = "file"


@dataclass
class ScanJob:
    kind: ScanKind
    targets: List[str]
    recursive: bool = True
    disinfect: bool = False
    auto_quarantine: bool = True
    scan_archives: bool = True
    exclusions: List[str] = field(default_factory=list)


class ScanEngine:
    """Thread-safe facade over kicomav.Scanner."""

    def __init__(self) -> None:
        self._scanner: Optional[Scanner] = None
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._scan_thread: Optional[threading.Thread] = None
        self._running = False
        self._engine_ready = False
        self._engine_error: Optional[str] = None
        self._active_scanner: Optional[Scanner] = None

    @property
    def is_scanning(self) -> bool:
        return self._running

    @property
    def is_ready(self) -> bool:
        return self._engine_ready

    @property
    def engine_error(self) -> Optional[str]:
        return self._engine_error

    @property
    def version(self) -> str:
        return getattr(kicomav, "__version__", "unknown")

    def _close_scanner(self, scanner: Optional[Scanner]) -> None:
        if scanner is None:
            return
        try:
            scanner.__exit__(None, None, None)
        except Exception:
            pass

    def _ensure_scanner(self) -> Scanner:
        with self._lock:
            if self._scanner is None:
                self._scanner = Scanner()
                self._scanner.__enter__()
            return self._scanner

    def _new_job_scanner(self) -> Scanner:
        scanner = Scanner()
        scanner.__enter__()
        return scanner

    def warm_up(self) -> bool:
        try:
            configure_kicomav_environment()
            self._ensure_scanner()
            self._engine_ready = True
            self._engine_error = None
            return True
        except Exception as exc:
            logger.exception("Engine warm-up failed: %s", exc)
            self._engine_ready = False
            self._engine_error = str(exc)
            return False

    def close(self) -> None:
        with self._lock:
            self._close_scanner(self._active_scanner)
            self._active_scanner = None
            self._close_scanner(self._scanner)
            self._scanner = None
        self._engine_ready = False

    def cancel_scan(self) -> None:
        self._cancel.set()

    def _scan_with_timeout(
        self,
        scanner: Scanner,
        fpath: str,
        *,
        disinfect: bool,
        scan_archives: bool,
    ) -> ScanResult:
        if self._cancel.is_set():
            return ScanResult(path=fpath, error="cancelled")

        budget = timeout_for_path(fpath)
        result_box: List[ScanResult] = []

        def run() -> None:
            try:
                result_box.append(
                    scan_path_comprehensive(
                        scanner,
                        fpath,
                        disinfect=disinfect,
                        scan_archives=scan_archives,
                    )
                )
            except Exception as exc:
                logger.exception("Scan failed for %s: %s", fpath, exc)
                result_box.append(ScanResult(path=fpath, error=str(exc)))

        worker = threading.Thread(target=run, daemon=True, name="asav-file-scan")
        worker.start()
        deadline = time.time() + budget
        while worker.is_alive() and time.time() < deadline:
            if self._cancel.is_set():
                self._close_scanner(scanner)
                return ScanResult(path=fpath, error="cancelled")
            worker.join(0.25)

        if self._cancel.is_set():
            self._close_scanner(scanner)
            return ScanResult(path=fpath, error="cancelled")

        if worker.is_alive():
            logger.warning("Scan timed out after %.0fs: %s", budget, fpath)
            self._close_scanner(scanner)
            return ScanResult(path=fpath, error=f"timed out after {int(budget)}s")

        return result_box[0] if result_box else ScanResult(path=fpath, error="scan failed")

    def _is_excluded(self, path: str, patterns: List[str]) -> bool:
        if not patterns:
            return False
        normalized = path.replace("/", "\\").lower()
        for pattern in patterns:
            p = pattern.replace("/", "\\").lower()
            if fnmatch.fnmatch(normalized, p) or fnmatch.fnmatch(normalized, f"*{p}*"):
                return True
            if p.endswith("\\") and normalized.startswith(p):
                return True
            if normalized.startswith(p.rstrip("\\") + "\\"):
                return True
        return False

    def _prune_walk_dirs(self, root: str, dirs: List[str], exclusions: List[str]) -> None:
        kept: List[str] = []
        for name in dirs:
            if name in SKIP_DIR_NAMES:
                continue
            sub = os.path.join(root, name)
            if self._is_excluded(sub, exclusions):
                continue
            kept.append(name)
        dirs[:] = kept

    def _iter_files(
        self,
        targets: List[str],
        recursive: bool,
        exclusions: List[str],
    ) -> Generator[str, None, None]:
        seen: set[str] = set()

        for target in targets:
            if self._cancel.is_set():
                return
            if not os.path.exists(target):
                continue

            if os.path.isfile(target):
                fpath = os.path.abspath(target)
                if fpath not in seen and not self._is_excluded(fpath, exclusions):
                    if not quarantine_mod.is_quarantined_path(fpath):
                        seen.add(fpath)
                        yield fpath
                continue

            if not os.path.isdir(target):
                continue

            if not recursive:
                try:
                    names = os.listdir(target)
                except OSError:
                    continue
                for name in names:
                    fpath = os.path.join(target, name)
                    if os.path.isfile(fpath):
                        fpath = os.path.abspath(fpath)
                        if fpath not in seen and not self._is_excluded(fpath, exclusions):
                            if not quarantine_mod.is_quarantined_path(fpath):
                                seen.add(fpath)
                                yield fpath
                continue

            try:
                for root, dirs, files in os.walk(target, topdown=True, followlinks=False):
                    if self._cancel.is_set():
                        return
                    self._prune_walk_dirs(root, dirs, exclusions)
                    for name in files:
                        fpath = os.path.join(root, name)
                        try:
                            if not os.path.isfile(fpath):
                                continue
                            if os.path.getsize(fpath) > MAX_SCAN_FILE_BYTES:
                                continue
                        except OSError:
                            continue
                        fpath = os.path.abspath(fpath)
                        if fpath in seen or self._is_excluded(fpath, exclusions):
                            continue
                        if quarantine_mod.is_quarantined_path(fpath):
                            continue
                        seen.add(fpath)
                        yield fpath
            except OSError as exc:
                logger.warning("Cannot walk %s: %s", target, exc)

    def scan_path_sync(
        self,
        path: str,
        disinfect: bool = False,
        scan_archives: bool = True,
    ) -> ScanResult:
        if self._running:
            return ScanResult(path=path, error="batch scan in progress")
        if not self._engine_ready:
            self.warm_up()
        scanner = self._ensure_scanner()
        with self._lock:
            return scan_path_comprehensive(
                scanner,
                path,
                disinfect=disinfect,
                scan_archives=scan_archives,
            )

    def scan_file_sync(self, path: str, disinfect: bool = False) -> ScanResult:
        return self.scan_path_sync(path, disinfect=disinfect, scan_archives=True)

    def start_scan(
        self,
        job: ScanJob,
        on_phase: Optional[PhaseCallback] = None,
        on_progress: Optional[ProgressCallback] = None,
        on_threat: Optional[ThreatCallback] = None,
        on_finished: Optional[FinishedCallback] = None,
    ) -> bool:
        if self._running:
            return False
        self._cancel.clear()
        self._running = True

        def worker() -> None:
            stats = {
                "files_scanned": 0,
                "threats": 0,
                "quarantined": 0,
                "errors": 0,
                "timeouts": 0,
                "cancelled": False,
                "engine_error": False,
            }
            job_scanner: Optional[Scanner] = None
            try:
                if on_phase:
                    on_phase("Starting KicomAV engine...")
                if not self.warm_up():
                    stats["engine_error"] = True
                    stats["errors"] += 1
                    if on_phase:
                        on_phase(self._engine_error or "Engine failed to start.")
                    return

                job_scanner = self._new_job_scanner()
                self._active_scanner = job_scanner

                for target in job.targets:
                    if self._cancel.is_set():
                        stats["cancelled"] = True
                        break
                    if on_phase:
                        on_phase(f"Scanning location: {target}")

                    for fpath in self._iter_files([target], job.recursive, job.exclusions):
                        if self._cancel.is_set():
                            stats["cancelled"] = True
                            break

                        stats["files_scanned"] += 1
                        current = stats["files_scanned"]
                        if on_progress:
                            on_progress(fpath, current, 0)

                        if job_scanner is None:
                            job_scanner = self._new_job_scanner()
                            self._active_scanner = job_scanner

                        result = self._scan_with_timeout(
                            job_scanner,
                            fpath,
                            disinfect=job.disinfect,
                            scan_archives=job.scan_archives,
                        )

                        if result.error == "cancelled":
                            stats["cancelled"] = True
                            break
                        if result.error and result.error.startswith("timed out"):
                            stats["timeouts"] += 1
                            stats["errors"] += 1
                            job_scanner = self._new_job_scanner()
                            self._active_scanner = job_scanner
                            continue
                        if result.error:
                            stats["errors"] += 1
                        if result.infected:
                            stats["threats"] += 1
                            if on_threat:
                                on_threat(result)
                            if job.auto_quarantine and not result.disinfected:
                                q = quarantine_mod.quarantine_file(
                                    result.path,
                                    result.malware_name or "Unknown",
                                )
                                if q:
                                    stats["quarantined"] += 1
            finally:
                self._close_scanner(job_scanner)
                self._active_scanner = None
                self._running = False
                if on_finished:
                    on_finished(stats)

        self._scan_thread = threading.Thread(target=worker, daemon=True, name="asav-scan")
        self._scan_thread.start()
        return True

    def update_signatures(
        self,
        on_status: Optional[Callable[[str], None]] = None,
        on_done: Optional[Callable[[object], None]] = None,
    ) -> None:
        def worker() -> None:
            try:
                configure_kicomav_environment()
                if on_status:
                    on_status("Checking for signature updates...")
                result = kicomav.update()
                if on_status and result.updated_files:
                    on_status(f"Updated {len(result.updated_files)} signature file(s).")
                elif on_status:
                    on_status("Signatures are up to date.")
                if on_done:
                    on_done(result)
            except Exception as exc:
                logger.exception("Update failed: %s", exc)
                if on_status:
                    on_status(f"Update failed: {exc}")
                if on_done:
                    on_done(None)

        threading.Thread(target=worker, daemon=True, name="asav-update").start()


def build_job(kind: ScanKind, targets: List[str], cfg: AppConfig) -> ScanJob:
    return ScanJob(
        kind=kind,
        targets=targets,
        recursive=True,
        auto_quarantine=cfg.auto_quarantine,
        scan_archives=cfg.scan_archives,
        exclusions=list(cfg.exclusions),
    )
