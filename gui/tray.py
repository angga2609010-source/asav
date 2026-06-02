"""System tray integration for background operation."""

from __future__ import annotations

import threading
from typing import Callable, Optional

from PIL import Image, ImageDraw


def build_tray_image() -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((2, 2, 62, 62), fill="#1f6feb", outline="#0d419d")
    draw.polygon([(32, 14), (48, 28), (48, 46), (16, 46), (16, 28)], fill="#ffffff")
    draw.rectangle((28, 34, 36, 46), fill="#1f6feb")
    return img


class TrayIcon:
    """Runs pystray in a background thread."""

    def __init__(
        self,
        on_show: Callable[[], None],
        on_exit: Callable[[], None],
        tooltip: str = "ASAV — KicomAV Protection",
    ) -> None:
        self._on_show = on_show
        self._on_exit = on_exit
        self._tooltip = tooltip
        self._icon = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()

    @property
    def running(self) -> bool:
        return self._icon is not None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        def runner() -> None:
            import pystray

            menu = pystray.Menu(
                pystray.MenuItem("Open ASAV", lambda: self._on_show()),
                pystray.MenuItem("Exit", lambda: self._on_exit()),
            )
            self._icon = pystray.Icon(
                "asav",
                build_tray_image(),
                self._tooltip,
                menu,
            )
            self._ready.set()
            self._icon.run()

        self._ready.clear()
        self._thread = threading.Thread(target=runner, daemon=True, name="asav-tray")
        self._thread.start()
        self._ready.wait(timeout=5)

    def stop(self) -> None:
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None

    def notify(self, title: str, message: str) -> None:
        if self._icon:
            try:
                self._icon.notify(message, title)
            except Exception:
                pass
