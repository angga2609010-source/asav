"""Lightweight startup splash (Discord / Steam style)."""

from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from typing import Optional, Tuple

# Theme aligned with main ASAV UI
BG = "#171a21"
BG_ACCENT = "#1f6feb"
TEXT = "#e6edf3"
TEXT_DIM = "#8b949e"
MIN_SHOW_MS = 1400


@dataclass
class PreloadResult:
    cfg: object
    engine: object
    sig_ok: bool = True
    sig_message: str = ""
    engine_ready: bool = False


class SplashScreen:
    """Borderless centered splash using tkinter only (fast startup)."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.configure(bg=BG)
        self.root.attributes("-topmost", True)

        self._updates: queue.Queue[Tuple[str, float]] = queue.Queue()
        self._width = 460
        self._height = 280
        self._center_window()

        frame = tk.Frame(self.root, bg=BG, highlightthickness=1, highlightbackground="#2d333b")
        frame.pack(fill="both", expand=True, padx=1, pady=1)

        tk.Label(
            frame,
            text="ASAV",
            font=("Segoe UI", 32, "bold"),
            fg=TEXT,
            bg=BG,
        ).pack(pady=(36, 4))

        tk.Label(
            frame,
            text="KicomAV Protection",
            font=("Segoe UI", 11),
            fg=TEXT_DIM,
            bg=BG,
        ).pack(pady=(0, 28))

        self._status = tk.Label(
            frame,
            text="Starting…",
            font=("Segoe UI", 10),
            fg=TEXT_DIM,
            bg=BG,
        )
        self._status.pack(pady=(0, 10))

        bar_bg = tk.Frame(frame, bg="#0d1117", height=4, width=320)
        bar_bg.pack(pady=(0, 8))
        bar_bg.pack_propagate(False)

        self._bar_fill = tk.Frame(bar_bg, bg=BG_ACCENT, height=4, width=0)
        self._bar_fill.place(x=0, y=0, relheight=1)

        self._bar_max = 320

        tk.Label(
            frame,
            text="Powered by KicomAV",
            font=("Segoe UI", 8),
            fg="#57606a",
            bg=BG,
        ).pack(side="bottom", pady=14)

        self.root.update_idletasks()
        self._poll_after_id: str | None = None
        self._tick_after_id: str | None = None
        self._poll()

    def _center_window(self) -> None:
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - self._width) // 2
        y = (sh - self._height) // 2
        self.root.geometry(f"{self._width}x{self._height}+{x}+{y}")

    def _poll(self) -> None:
        try:
            while True:
                text, progress = self._updates.get_nowait()
                self._status.config(text=text)
                width = max(0, min(self._bar_max, int(self._bar_max * progress)))
                self._bar_fill.place(x=0, y=0, width=width, relheight=1)
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self._poll_after_id = self.root.after(40, self._poll)

    def _cancel_pending_after(self) -> None:
        for after_id in (self._poll_after_id, self._tick_after_id):
            if after_id:
                try:
                    self.root.after_cancel(after_id)
                except tk.TclError:
                    pass
        try:
            for after_id in self.root.tk.call("after", "info"):
                self.root.after_cancel(after_id)
        except tk.TclError:
            pass
        self._poll_after_id = None
        self._tick_after_id = None

    def set_progress(self, text: str, progress: float) -> None:
        self._updates.put((text, max(0.0, min(1.0, progress))))

    def run_until_done(self, done: threading.Event) -> None:
        started = time.time()

        def tick() -> None:
            if done.is_set() and (time.time() - started) * 1000 >= MIN_SHOW_MS:
                self.root.quit()
                return
            self._tick_after_id = self.root.after(40, tick)

        self._tick_after_id = self.root.after(40, tick)
        self.root.mainloop()

    def close(self) -> None:
        self._cancel_pending_after()
        try:
            self.root.quit()
        except tk.TclError:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        teardown_tkinter_after_splash()


def teardown_tkinter_after_splash() -> None:
    """Release the splash Tk root so CustomTkinter can create a clean main window."""
    import gc

    import tkinter

    try:
        tkinter._default_root = None  # type: ignore[attr-defined]
    except Exception:
        pass
    gc.collect()


def _preload_worker(splash: SplashScreen, result: PreloadResult, done: threading.Event) -> None:
    try:
        from asav.config import load_config
        from asav.engine import ScanEngine
        from asav.kicomav_setup import bootstrap_signatures

        splash.set_progress("Loading settings…", 0.12)
        result.cfg = load_config()

        splash.set_progress("Checking threat signatures…", 0.42)
        ok, msg = bootstrap_signatures()
        result.sig_ok = ok
        result.sig_message = msg

        splash.set_progress("Starting protection engine…", 0.72)
        result.engine = ScanEngine()
        result.engine_ready = result.engine.warm_up()

        ver = getattr(result.engine, "version", "")
        splash.set_progress(f"Ready — KicomAV {ver}" if ver else "Ready", 1.0)
    except Exception as exc:
        splash.set_progress(f"Startup issue: {exc}", 1.0)
        result.sig_message = str(exc)
    finally:
        done.set()


def run_startup_splash() -> Optional[PreloadResult]:
    """Show splash, run preload, return data for the main window."""
    splash = SplashScreen()
    result = PreloadResult(cfg=None, engine=None)
    done = threading.Event()

    threading.Thread(
        target=_preload_worker,
        args=(splash, result, done),
        daemon=True,
        name="asav-splash-preload",
    ).start()

    splash.run_until_done(done)
    splash.close()
    return result if result.cfg is not None and result.engine is not None else None
