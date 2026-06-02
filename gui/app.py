"""ASAV main window — CustomTkinter UI over KicomAV."""

from __future__ import annotations

import queue
import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk

from asav.config import load_config, save_config
from asav.engine import ScanEngine, ScanKind, build_job
from asav.kicomav_setup import bootstrap_signatures
from asav.paths import full_scan_paths, quick_scan_paths
from asav.quarantine import delete_entry, list_quarantined, restore_entry
from asav.realtime import RealtimeGuard
from asav import startup as startup_mod
from gui.tray import TrayIcon
from gui.splash import PreloadResult

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

ACCENT = "#1f6feb"
DANGER = "#da3633"
SUCCESS = "#3fb950"
BG_PANEL = ("#f0f2f5", "#1c2128")
TEXT_MUTED = ("#57606a", "#8b949e")


class ASAVApp(ctk.CTk):
    def __init__(
        self,
        *,
        start_hidden: bool = False,
        preload: PreloadResult | None = None,
    ) -> None:
        super().__init__()
        self.title("ASAV — KicomAV Protection")
        self.geometry("1120x720")
        self.minsize(960, 600)

        if preload and preload.cfg and preload.engine:
            self.cfg = preload.cfg
            self.engine = preload.engine
            self._preloaded = True
        else:
            self.cfg = load_config()
            self.engine = ScanEngine()
            self._preloaded = False

        self.realtime = RealtimeGuard(self.engine, self.cfg)
        self.tray: TrayIcon | None = None
        self._force_quit = False
        self._start_hidden = start_hidden

        self._current_page = "dashboard"
        self._last_scan_stats: dict = {}
        self._threat_rows: list[ctk.CTkFrame] = []
        self._ui_queue: queue.Queue = queue.Queue()
        self._scan_progress_mode = "determinate"

        self._build_layout()
        self._show_page("dashboard")
        self._refresh_quarantine_list()
        self._sync_realtime_from_config()
        self._drain_ui_queue()

        if self._preloaded and preload:
            self._apply_preload_state(preload)
        else:
            self._start_background_init()

        self._ensure_tray()

        if self._start_hidden and self.cfg.minimize_to_tray:
            self.after(150, self._hide_to_tray)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _apply_preload_state(self, preload: PreloadResult) -> None:
        if preload.engine_ready:
            self.lbl_engine_ver.configure(
                text=f"KicomAV engine v{self.engine.version} — ready"
            )
        else:
            err = self.engine.engine_error or "unknown error"
            self.lbl_engine_ver.configure(text=f"Engine failed: {err}")
        if preload.sig_message:
            self._log(f"Signatures: {preload.sig_message}")

    def _post_ui(self, event: str, *args) -> None:
        """Schedule UI work on the main Tk thread."""
        self._ui_queue.put((event, args))

    def _drain_ui_queue(self) -> None:
        try:
            while True:
                event, args = self._ui_queue.get_nowait()
                if event == "progress":
                    self._on_scan_progress(*args)
                elif event == "phase":
                    self._on_scan_phase(*args)
                elif event == "threat":
                    self._on_threat(*args)
                elif event == "finished":
                    self._on_scan_finished(*args)
                elif event == "log":
                    self._log(*args)
                elif event == "engine_ready":
                    self._on_engine_ready(*args)
                elif event == "sig_status":
                    self._on_sig_status(*args)
                elif event == "realtime_threat":
                    self._handle_realtime_threat(*args)
        except queue.Empty:
            pass
        self.after(80, self._drain_ui_queue)

    def _start_background_init(self) -> None:
        self.lbl_engine_ver.configure(text=f"KicomAV v{self.engine.version} — starting engine…")

        def work() -> None:
            ok_sig, sig_msg = bootstrap_signatures()
            self._post_ui("sig_status", ok_sig, sig_msg)
            ready = self.engine.warm_up()
            self._post_ui("engine_ready", ready)

        threading.Thread(target=work, daemon=True, name="asav-init").start()

    def _on_engine_ready(self, ready: bool) -> None:
        if ready:
            self.lbl_engine_ver.configure(
                text=f"KicomAV engine v{self.engine.version} — ready"
            )
        else:
            err = self.engine.engine_error or "unknown error"
            self.lbl_engine_ver.configure(text=f"Engine failed: {err}")

    def _on_sig_status(self, ok: bool, message: str) -> None:
        if ok:
            self._log(f"Signatures: {message}")
        else:
            self._log(f"Signature setup: {message}")

    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(8, weight=1)

        ctk.CTkLabel(
            self.sidebar,
            text="ASAV",
            font=ctk.CTkFont(size=26, weight="bold"),
        ).grid(row=0, column=0, padx=24, pady=(28, 4), sticky="w")
        ctk.CTkLabel(
            self.sidebar,
            text="Powered by KicomAV",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_MUTED,
        ).grid(row=1, column=0, padx=24, pady=(0, 20), sticky="w")

        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        for i, (key, label) in enumerate(
            [
                ("dashboard", "Dashboard"),
                ("scan", "Scan"),
                ("quarantine", "Quarantine"),
                ("settings", "Settings"),
            ],
            start=2,
        ):
            btn = ctk.CTkButton(
                self.sidebar,
                text=label,
                anchor="w",
                fg_color="transparent",
                text_color=("gray10", "gray90"),
                hover_color=("gray85", "gray25"),
                height=40,
                command=lambda k=key: self._show_page(k),
            )
            btn.grid(row=i, column=0, padx=16, pady=4, sticky="ew")
            self._nav_buttons[key] = btn

        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self.pages: dict[str, ctk.CTkFrame] = {}
        self.pages["dashboard"] = self._build_dashboard()
        self.pages["scan"] = self._build_scan_page()
        self.pages["quarantine"] = self._build_quarantine_page()
        self.pages["settings"] = self._build_settings_page()

    def _highlight_nav(self, active: str) -> None:
        for key, btn in self._nav_buttons.items():
            if key == active:
                btn.configure(fg_color=ACCENT, hover_color=ACCENT)
            else:
                btn.configure(fg_color="transparent", hover_color=("gray85", "gray25"))

    def _show_page(self, name: str) -> None:
        self._current_page = name
        self._highlight_nav(name)
        for page in self.pages.values():
            page.grid_forget()
        self.pages[name].grid(row=0, column=0, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

    def _panel(self, parent: ctk.CTkBaseClass, **kwargs) -> ctk.CTkFrame:
        return ctk.CTkFrame(parent, fg_color=BG_PANEL, corner_radius=12, **kwargs)

    def _build_dashboard(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self.content, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)

        header = ctk.CTkLabel(
            frame,
            text="Protection overview",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        header.grid(row=0, column=0, sticky="w", pady=(0, 16))

        status_panel = self._panel(frame)
        status_panel.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        status_panel.grid_columnconfigure(1, weight=1)

        self.lbl_protection = ctk.CTkLabel(
            status_panel,
            text="● Protected",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=SUCCESS,
        )
        self.lbl_protection.grid(row=0, column=0, padx=24, pady=20, sticky="w")

        self.lbl_engine_ver = ctk.CTkLabel(
            status_panel,
            text=f"KicomAV engine v{self.engine.version}",
            text_color=TEXT_MUTED,
        )
        self.lbl_engine_ver.grid(row=1, column=0, padx=24, pady=(0, 20), sticky="w")

        self.realtime_switch = ctk.CTkSwitch(
            status_panel,
            text="Real-time protection",
            command=self._toggle_realtime,
        )
        self.realtime_switch.grid(row=0, column=1, padx=24, pady=20, sticky="e")
        if self.cfg.realtime_enabled:
            self.realtime_switch.select()

        actions = self._panel(frame)
        actions.grid(row=2, column=0, sticky="ew")
        actions.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkButton(
            actions,
            text="Quick scan",
            height=48,
            command=lambda: self._start_preset_scan(ScanKind.QUICK),
        ).grid(row=0, column=0, padx=16, pady=16, sticky="ew")
        ctk.CTkButton(
            actions,
            text="Full scan",
            height=48,
            fg_color="#6e40c9",
            hover_color="#5a32a8",
            command=lambda: self._start_preset_scan(ScanKind.FULL),
        ).grid(row=0, column=1, padx=16, pady=16, sticky="ew")
        ctk.CTkButton(
            actions,
            text="Update signatures",
            height=48,
            fg_color="#238636",
            hover_color="#196c2e",
            command=self._update_signatures,
        ).grid(row=0, column=2, padx=16, pady=16, sticky="ew")

        self.lbl_last_scan = ctk.CTkLabel(
            frame,
            text="No scans run yet.",
            text_color=TEXT_MUTED,
            justify="left",
        )
        self.lbl_last_scan.grid(row=3, column=0, sticky="w", pady=12)

        self.lbl_tray_hint = ctk.CTkLabel(
            frame,
            text="Tip: enable background mode in Settings to keep protection active in the system tray.",
            text_color=TEXT_MUTED,
            wraplength=800,
            justify="left",
        )
        self.lbl_tray_hint.grid(row=4, column=0, sticky="w")

        return frame

    def _build_scan_page(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self.content, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            frame,
            text="Scan center",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 12))

        toolbar = ctk.CTkFrame(frame, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        toolbar.grid_columnconfigure(4, weight=1)

        ctk.CTkButton(toolbar, text="Quick", width=100, command=lambda: self._start_preset_scan(ScanKind.QUICK)).grid(
            row=0, column=0, padx=(0, 8)
        )
        ctk.CTkButton(
            toolbar,
            text="Full",
            width=100,
            command=lambda: self._start_preset_scan(ScanKind.FULL),
        ).grid(row=0, column=1, padx=8)
        ctk.CTkButton(
            toolbar,
            text="Browse…",
            width=100,
            command=self._browse_custom_scan,
        ).grid(row=0, column=2, padx=8)
        self.btn_cancel = ctk.CTkButton(
            toolbar,
            text="Cancel",
            width=100,
            fg_color=DANGER,
            hover_color="#b62324",
            state="disabled",
            command=self._cancel_scan,
        )
        self.btn_cancel.grid(row=0, column=3, padx=8)

        prog_panel = self._panel(frame)
        prog_panel.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        prog_panel.grid_columnconfigure(0, weight=1)

        self.lbl_scan_file = ctk.CTkLabel(
            prog_panel,
            text="Ready to scan",
            anchor="w",
        )
        self.lbl_scan_file.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")

        self.progress = ctk.CTkProgressBar(prog_panel)
        self.progress.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="ew")
        self.progress.set(0)

        self.lbl_scan_stats = ctk.CTkLabel(
            prog_panel,
            text="0 / 0 files",
            text_color=TEXT_MUTED,
        )
        self.lbl_scan_stats.grid(row=2, column=0, padx=16, pady=(0, 16), sticky="w")

        bottom = ctk.CTkFrame(frame, fg_color="transparent")
        bottom.grid(row=3, column=0, sticky="nsew")
        bottom.grid_columnconfigure(0, weight=1)
        bottom.grid_columnconfigure(1, weight=1)
        bottom.grid_rowconfigure(0, weight=1)

        log_panel = self._panel(bottom)
        log_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        log_panel.grid_rowconfigure(1, weight=1)
        log_panel.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(log_panel, text="Scan log", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=12, pady=12, sticky="w"
        )
        self.scan_log = ctk.CTkTextbox(log_panel, wrap="none")
        self.scan_log.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")

        threat_panel = self._panel(bottom)
        threat_panel.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        threat_panel.grid_rowconfigure(1, weight=1)
        threat_panel.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(threat_panel, text="Threats found", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=12, pady=12, sticky="w"
        )
        self.threat_list = ctk.CTkScrollableFrame(threat_panel)
        self.threat_list.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")

        return frame

    def _build_quarantine_page(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self.content, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            frame,
            text="Quarantine",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 12))

        self.quarantine_scroll = ctk.CTkScrollableFrame(frame)
        self.quarantine_scroll.grid(row=1, column=0, sticky="nsew")
        self.quarantine_scroll.grid_columnconfigure(0, weight=1)

        return frame

    def _build_settings_page(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self.content, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame,
            text="Settings",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 16))

        panel = self._panel(frame)
        panel.grid(row=1, column=0, sticky="ew")
        panel.grid_columnconfigure(1, weight=1)

        self.switch_auto_quarantine = ctk.CTkSwitch(
            panel,
            text="Automatically quarantine threats",
            command=self._save_settings_from_ui,
        )
        self.switch_auto_quarantine.grid(row=0, column=0, columnspan=2, padx=20, pady=16, sticky="w")
        if self.cfg.auto_quarantine:
            self.switch_auto_quarantine.select()

        self.switch_scan_archives = ctk.CTkSwitch(
            panel,
            text="Scan inside ZIP archives (recommended)",
            command=self._save_settings_from_ui,
        )
        self.switch_scan_archives.grid(row=1, column=0, columnspan=2, padx=20, pady=(0, 16), sticky="w")
        if self.cfg.scan_archives:
            self.switch_scan_archives.select()

        startup_panel = self._panel(frame)
        startup_panel.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        startup_panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            startup_panel,
            text="Startup & background",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, padx=20, pady=(16, 8), sticky="w")

        self.switch_run_at_startup = ctk.CTkSwitch(
            startup_panel,
            text="Run ASAV when Windows starts",
            command=self._save_settings_from_ui,
        )
        self.switch_run_at_startup.grid(row=1, column=0, padx=20, pady=8, sticky="w")
        if self.cfg.run_at_startup:
            self.switch_run_at_startup.select()

        self.switch_start_in_tray = ctk.CTkSwitch(
            startup_panel,
            text="Start minimized to system tray on boot",
            command=self._save_settings_from_ui,
        )
        self.switch_start_in_tray.grid(row=2, column=0, padx=20, pady=8, sticky="w")
        if self.cfg.start_in_tray:
            self.switch_start_in_tray.select()

        self.switch_minimize_to_tray = ctk.CTkSwitch(
            startup_panel,
            text="Keep running in background when window is closed (system tray)",
            command=self._save_settings_from_ui,
        )
        self.switch_minimize_to_tray.grid(row=3, column=0, padx=20, pady=(8, 16), sticky="w")
        if self.cfg.minimize_to_tray:
            self.switch_minimize_to_tray.select()

        ctk.CTkLabel(
            startup_panel,
            text="Closing the window hides ASAV to the tray so real-time protection can stay on.",
            text_color=TEXT_MUTED,
            wraplength=720,
            justify="left",
        ).grid(row=4, column=0, padx=20, pady=(0, 16), sticky="w")

        ctk.CTkLabel(panel, text="Exclusion path (glob ok):").grid(
            row=2, column=0, padx=20, pady=8, sticky="w"
        )
        self.entry_exclusion = ctk.CTkEntry(panel, placeholder_text=r"C:\Games\*")
        self.entry_exclusion.grid(row=2, column=1, padx=20, pady=8, sticky="ew")

        ctk.CTkButton(panel, text="Add exclusion", command=self._add_exclusion).grid(
            row=3, column=1, padx=20, pady=8, sticky="e"
        )

        self.exclusion_list = ctk.CTkTextbox(panel, height=120)
        self.exclusion_list.grid(row=4, column=0, columnspan=2, padx=20, pady=12, sticky="ew")
        self._refresh_exclusion_list()

        from asav.config import APP_DIR

        ctk.CTkLabel(
            frame,
            text=f"Config, quarantine, signatures: {APP_DIR}",
            text_color=TEXT_MUTED,
        ).grid(row=3, column=0, sticky="w", pady=12)

        return frame

    def _log(self, message: str) -> None:
        self.scan_log.insert("end", message + "\n")
        self.scan_log.see("end")

    def _clear_threats_ui(self) -> None:
        for row in self._threat_rows:
            row.destroy()
        self._threat_rows.clear()

    def _add_threat_ui(self, path: str, malware: str) -> None:
        row = ctk.CTkFrame(self.threat_list, fg_color=("gray90", "gray20"))
        row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            row,
            text=malware,
            font=ctk.CTkFont(weight="bold"),
            text_color=DANGER,
        ).grid(row=0, column=0, padx=10, pady=(8, 0), sticky="w")
        ctk.CTkLabel(row, text=path, anchor="w", wraplength=400).grid(
            row=1, column=0, padx=10, pady=(0, 8), sticky="w"
        )
        row.pack(fill="x", pady=4)
        self._threat_rows.append(row)

    def _start_preset_scan(self, kind: ScanKind) -> None:
        if self.engine.is_scanning:
            messagebox.showwarning("Scan in progress", "Wait for the current scan to finish or cancel it.")
            return
        if kind == ScanKind.QUICK:
            targets = quick_scan_paths()
        elif kind == ScanKind.FULL:
            if not messagebox.askyesno(
                "Full scan",
                "A full scan checks all drives and may take a long time. Continue?",
            ):
                return
            targets = full_scan_paths()
        else:
            return
        if not targets:
            messagebox.showerror("Scan", "No valid scan targets found.")
            return
        self._show_page("scan")
        self._run_scan(kind, targets)

    def _browse_custom_scan(self) -> None:
        if self.engine.is_scanning:
            messagebox.showwarning("Scan in progress", "Cancel the current scan first.")
            return
        path = filedialog.askdirectory(title="Select folder to scan") or filedialog.askopenfilename(
            title="Or select a file to scan"
        )
        if not path:
            return
        self._show_page("scan")
        self._run_scan(ScanKind.CUSTOM, [path])

    def _run_scan(self, kind: ScanKind, targets: list[str]) -> None:
        self._clear_threats_ui()
        self.scan_log.delete("1.0", "end")
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self._scan_progress_mode = "indeterminate"
        self.btn_cancel.configure(state="normal", text="Cancel")
        self.lbl_scan_file.configure(text="Preparing scan…")
        self.lbl_scan_stats.configure(text="0 files scanned")
        self._log(f"Starting {kind.value} scan…")
        for t in targets:
            self._log(f"  Target: {t}")

        job = build_job(kind, targets, self.cfg)

        def on_phase(message: str) -> None:
            self._post_ui("phase", message)

        def on_progress(path: str, current: int, total: int) -> None:
            self._post_ui("progress", path, current, total)

        def on_threat(result) -> None:
            self._post_ui("threat", result)

        def on_finished(stats: dict) -> None:
            self._post_ui("finished", stats)

        self.engine.start_scan(job, on_phase, on_progress, on_threat, on_finished)

    def _on_scan_phase(self, message: str) -> None:
        self.lbl_scan_file.configure(text=message)
        self._log(message)

    def _on_scan_progress(self, path: str, current: int, total: int) -> None:
        display = path if len(path) < 90 else "…" + path[-87:]
        self.lbl_scan_file.configure(text=display)
        if total > 0:
            if self._scan_progress_mode != "determinate":
                self.progress.stop()
                self.progress.configure(mode="determinate")
                self._scan_progress_mode = "determinate"
            self.lbl_scan_stats.configure(text=f"{current} / {total} files")
            self.progress.set(current / total)
        else:
            self.lbl_scan_stats.configure(text=f"{current} files scanned")

    def _on_threat(self, result) -> None:
        name = result.malware_name or "Unknown"
        self._log(f"THREAT: {name} — {result.path}")
        self._add_threat_ui(result.path, name)

    def _on_scan_finished(self, stats: dict) -> None:
        self._last_scan_stats = stats
        self.btn_cancel.configure(state="disabled", text="Cancel")
        if self._scan_progress_mode == "indeterminate":
            self.progress.stop()
            self.progress.configure(mode="determinate")
            self._scan_progress_mode = "determinate"
        self.progress.set(1 if stats.get("files_scanned") else 0)
        cancelled = " (cancelled)" if stats.get("cancelled") else ""
        timeout_note = ""
        if stats.get("timeouts"):
            timeout_note = f", Timeouts: {stats.get('timeouts', 0)}"
        if stats.get("engine_error"):
            summary = "Scan failed: KicomAV engine could not start. Try Update signatures, then scan again."
            messagebox.showerror("Scan failed", summary)
        else:
            summary = (
                f"Scan complete{cancelled}. "
                f"Files: {stats.get('files_scanned', 0)}, "
                f"Threats: {stats.get('threats', 0)}, "
                f"Quarantined: {stats.get('quarantined', 0)}, "
                f"Errors: {stats.get('errors', 0)}{timeout_note}"
            )
            if stats.get("threats", 0) > 0:
                messagebox.showwarning("Threats detected", summary)
        self._log(summary)
        self.lbl_scan_file.configure(text=summary)
        self.lbl_last_scan.configure(text=summary)
        self._refresh_quarantine_list()

    def _cancel_scan(self) -> None:
        self.engine.cancel_scan()
        self.btn_cancel.configure(state="disabled", text="Cancelling…")
        self.lbl_scan_file.configure(text="Cancelling scan — finishing current file…")
        self._log("Cancel requested — skipping remaining files after the current one finishes or times out.")

    def _toggle_realtime(self) -> None:
        enabled = bool(self.realtime_switch.get())
        self.cfg.realtime_enabled = enabled
        save_config(self.cfg)
        if enabled:
            ok = self.realtime.start(on_threat=self._on_realtime_threat)
            if not ok:
                self.realtime_switch.deselect()
                self.cfg.realtime_enabled = False
                save_config(self.cfg)
                messagebox.showerror(
                    "Real-time protection",
                    "Could not start monitoring. Check that watch paths exist.",
                )
            else:
                self.lbl_protection.configure(text="● Real-time protection ON", text_color=SUCCESS)
        else:
            self.realtime.stop()
            self.lbl_protection.configure(text="● Protected (on-demand)", text_color=SUCCESS)

    def _sync_realtime_from_config(self) -> None:
        if self.cfg.realtime_enabled:
            if self.realtime.start(on_threat=self._on_realtime_threat):
                self.realtime_switch.select()
                self.lbl_protection.configure(text="● Real-time protection ON", text_color=SUCCESS)

    def _on_realtime_threat(self, path: str, malware: str) -> None:
        self._post_ui("realtime_threat", path, malware)

    def _handle_realtime_threat(self, path: str, malware: str) -> None:
        self._log(f"[Realtime] {malware} — {path}")
        self._add_threat_ui(path, malware)
        self._refresh_quarantine_list()
        messagebox.showwarning("Threat blocked", f"{malware}\n{path}")

    def _update_signatures(self) -> None:
        self._log("Checking signature updates…")

        def status(msg: str) -> None:
            self._post_ui("log", msg)

        def done(result) -> None:
            if result and getattr(result, "package_update_available", False):
                ver = getattr(result, "latest_version", "?")

                def show() -> None:
                    messagebox.showinfo(
                        "Engine update",
                        f"A newer KicomAV package is available: {ver}\n"
                        "Run install.bat or: .venv\\Scripts\\python.exe -m pip install --upgrade kicomav",
                    )

                self._post_ui("log", f"Package update available: {ver}")
                self.after(0, show)

        self.engine.update_signatures(status, done)

    def _refresh_quarantine_list(self) -> None:
        for child in self.quarantine_scroll.winfo_children():
            child.destroy()
        entries = list_quarantined()
        if not entries:
            ctk.CTkLabel(
                self.quarantine_scroll,
                text="No quarantined items.",
                text_color=TEXT_MUTED,
            ).pack(pady=40)
            return
        for entry in reversed(entries):
            card = ctk.CTkFrame(self.quarantine_scroll, fg_color=("gray92", "gray18"))
            card.pack(fill="x", pady=6, padx=4)
            card.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(card, text=entry.malware_name, text_color=DANGER, font=ctk.CTkFont(weight="bold")).grid(
                row=0, column=0, padx=12, pady=(10, 0), sticky="w"
            )
            ctk.CTkLabel(card, text=entry.original_path, anchor="w").grid(
                row=1, column=0, padx=12, pady=2, sticky="w"
            )
            ctk.CTkLabel(
                card,
                text=entry.quarantined_at_str,
                text_color=TEXT_MUTED,
                font=ctk.CTkFont(size=11),
            ).grid(row=2, column=0, padx=12, pady=(0, 8), sticky="w")
            actions = ctk.CTkFrame(card, fg_color="transparent")
            actions.grid(row=0, column=1, rowspan=3, padx=12, pady=10)
            ctk.CTkButton(
                actions,
                text="Restore",
                width=80,
                command=lambda eid=entry.id: self._restore_quarantine(eid),
            ).pack(side="left", padx=4)
            ctk.CTkButton(
                actions,
                text="Delete",
                width=80,
                fg_color=DANGER,
                command=lambda eid=entry.id: self._delete_quarantine(eid),
            ).pack(side="left", padx=4)

    def _restore_quarantine(self, entry_id: str) -> None:
        if restore_entry(entry_id):
            self._refresh_quarantine_list()
            messagebox.showinfo("Quarantine", "File restored.")
        else:
            messagebox.showerror("Quarantine", "Could not restore file.")

    def _delete_quarantine(self, entry_id: str) -> None:
        if messagebox.askyesno("Delete", "Permanently delete this quarantined file?"):
            if delete_entry(entry_id):
                self._refresh_quarantine_list()
            else:
                messagebox.showerror("Quarantine", "Could not delete file.")

    def _refresh_exclusion_list(self) -> None:
        self.exclusion_list.delete("1.0", "end")
        for exc in self.cfg.exclusions:
            self.exclusion_list.insert("end", exc + "\n")

    def _add_exclusion(self) -> None:
        value = self.entry_exclusion.get().strip()
        if not value:
            return
        if value not in self.cfg.exclusions:
            self.cfg.exclusions.append(value)
            save_config(self.cfg)
            self._refresh_exclusion_list()
        self.entry_exclusion.delete(0, "end")

    def _ensure_tray(self) -> None:
        if self.tray is not None:
            return
        self.tray = TrayIcon(
            on_show=lambda: self.after(0, self._show_from_tray),
            on_exit=lambda: self.after(0, self._quit_from_tray),
        )
        self.tray.start()

    def _show_from_tray(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()
        self.attributes("-topmost", True)
        self.after(250, lambda: self.attributes("-topmost", False))

    def _hide_to_tray(self) -> None:
        self._ensure_tray()
        self.withdraw()
        if self.tray:
            self.tray.notify(
                "ASAV is running in the background",
                "Real-time protection stays active. Open ASAV from the tray icon.",
            )

    def _quit_from_tray(self) -> None:
        self._force_quit = True
        self._shutdown()

    def _save_settings_from_ui(self) -> None:
        self.cfg.auto_quarantine = bool(self.switch_auto_quarantine.get())
        self.cfg.scan_archives = bool(self.switch_scan_archives.get())
        self.cfg.run_at_startup = bool(self.switch_run_at_startup.get())
        self.cfg.start_in_tray = bool(self.switch_start_in_tray.get())
        self.cfg.minimize_to_tray = bool(self.switch_minimize_to_tray.get())
        save_config(self.cfg)

        ok = startup_mod.sync_startup(
            self.cfg.run_at_startup,
            start_in_tray=self.cfg.start_in_tray,
        )
        if self.cfg.run_at_startup and not ok:
            messagebox.showerror(
                "Startup",
                "Could not register ASAV for Windows startup.",
            )

    def _on_close(self) -> None:
        if self.cfg.minimize_to_tray and not self._force_quit:
            if self.engine.is_scanning:
                messagebox.showinfo(
                    "Background mode",
                    "Scan continues while ASAV runs in the system tray.\n"
                    "Open ASAV from the tray to view progress.",
                )
            self._hide_to_tray()
            return

        if self.engine.is_scanning:
            if not messagebox.askyesno("Exit", "A scan is running. Exit anyway?"):
                return
            self.engine.cancel_scan()
        self._shutdown()

    def _shutdown(self) -> None:
        self.realtime.stop()
        self.engine.close()
        if self.tray:
            self.tray.stop()
            self.tray = None
        self.destroy()


def run_app(*, start_hidden: bool = False, preload: PreloadResult | None = None) -> None:
    app = ASAVApp(start_hidden=start_hidden, preload=preload)
    app.mainloop()
