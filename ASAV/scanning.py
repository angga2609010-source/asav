"""Shared scan helpers — archive-aware scanning for KicomAV."""

from __future__ import annotations

import contextlib
import logging
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from kicomav import ScanResult, Scanner

logger = logging.getLogger(__name__)

ARCHIVE_EXTENSIONS = frozenset(
    {
        ".zip",
        ".7z",
        ".rar",
        ".tar",
        ".gz",
        ".bz2",
        ".xz",
        ".cab",
        ".egg",
        ".alz",
        ".iso",
    }
)

MAX_ZIP_ENTRIES = 80


def is_archive_path(path: str) -> bool:
    return Path(path).suffix.lower() in ARCHIVE_EXTENSIONS


def configure_scan_options(
    scanner: Scanner,
    path: str,
    *,
    disinfect: bool,
    scan_archives: bool,
) -> None:
    """Apply KicomAV flags. Archive deep-scan only for archive file types."""
    if not scanner._instance:
        scanner._ensure_initialized()
    if not scanner._instance:
        return
    use_arc = bool(scan_archives and is_archive_path(path))
    scanner._instance.set_options(
        {
            "opt_dis": disinfect,
            "opt_arc": use_arc,
            "opt_list": use_arc,
        }
    )


def scan_with_engine(
    scanner: Scanner,
    path: str,
    *,
    disinfect: bool = False,
    scan_archives: bool = True,
) -> ScanResult:
    configure_scan_options(scanner, path, disinfect=disinfect, scan_archives=scan_archives)
    return scanner.scan_file(path, disinfect=disinfect)


def _scan_zip_entries(scanner: Scanner, path: str, scan_archives: bool) -> Optional[ScanResult]:
    if not scan_archives:
        return None
    try:
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist()[:MAX_ZIP_ENTRIES]:
                if info.is_dir():
                    continue
                if info.file_size > 200 * 1024 * 1024:
                    continue
                try:
                    data = zf.read(info.filename)
                except (OSError, zipfile.BadZipFile, RuntimeError):
                    continue
                suffix = Path(info.filename).suffix or ".bin"
                fd, inner = tempfile.mkstemp(suffix=suffix, prefix="asav_")
                os.close(fd)
                try:
                    with open(inner, "wb") as handle:
                        handle.write(data)
                    inner_result = scan_with_engine(
                        scanner,
                        inner,
                        disinfect=False,
                        scan_archives=False,
                    )
                    if inner_result.infected:
                        return ScanResult(
                            path=f"{path} → {info.filename}",
                            infected=True,
                            malware_name=inner_result.malware_name,
                            disinfected=inner_result.disinfected,
                            error=inner_result.error,
                        )
                finally:
                    with contextlib.suppress(OSError):
                        os.remove(inner)
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        logger.debug("Supplemental zip scan skipped for %s: %s", path, exc)
    return None


def scan_path_comprehensive(
    scanner: Scanner,
    path: str,
    *,
    disinfect: bool = False,
    scan_archives: bool = True,
) -> ScanResult:
    primary = scan_with_engine(scanner, path, disinfect=disinfect, scan_archives=scan_archives)
    if primary.infected:
        return primary

    if scan_archives and path.lower().endswith(".zip"):
        inner = _scan_zip_entries(scanner, path, scan_archives)
        if inner and inner.infected:
            return ScanResult(
                path=path,
                infected=True,
                malware_name=f"{inner.malware_name} (in {inner.path.split(' → ', 1)[-1]})",
                disinfected=False,
                error=None,
            )

    return primary


def timeout_for_path(path: str) -> float:
    """Per-file scan budget in seconds (large files get more time, capped)."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return 45.0
    if size <= 5 * 1024 * 1024:
        return 45.0
    if size <= 50 * 1024 * 1024:
        return 90.0
    if size <= 200 * 1024 * 1024:
        return 120.0
    return 150.0
