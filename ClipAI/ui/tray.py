from __future__ import annotations

from collections.abc import Callable
import logging
import threading
import time

from PIL import Image, ImageDraw

from ClipAI.core.models import ApplicationStatus

logger = logging.getLogger("clipai.tray")

STATUS_COLORS: dict[ApplicationStatus, tuple[int, int, int]] = {
    "idle": (0, 82, 184),
    "processing": (255, 140, 0),
    "success": (0, 176, 79),
    "warning": (255, 215, 0),
    "error": (232, 17, 35),
    "paused": (107, 107, 107),
}


def create_tray_image(status: ApplicationStatus = "idle", *, memory_active: bool = False, size: int = 64) -> Image.Image:
    render_scale = 4
    width = height = size * render_scale
    scale = (size / 64.0) * render_scale
    image = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(image)
    thickness = int(14 * scale)
    gap = int(10 * scale)
    offset = int(16 * scale)
    cx, cy = width // 2, height // 2

    if memory_active:
        radius = int(7 * scale)
        dot_x = int(width * 0.80)
        dot_y = cy + int(15 * scale)
        draw.ellipse(
            (dot_x - radius, dot_y - radius, dot_x + radius, dot_y + radius),
            fill=(218, 165, 32),
            outline=(139, 101, 8),
            width=max(1, int(scale)),
        )

    color = STATUS_COLORS[status]
    draw.line(
        ((cx - offset // 2 - gap, cy + int(20 * scale)), (cx - offset // 2 + gap, cy - int(20 * scale))),
        fill=color,
        width=thickness,
    )
    draw.line(
        ((cx + offset // 2 - gap, cy + int(15 * scale)), (cx + offset // 2 + gap, cy - int(15 * scale))),
        fill=color,
        width=thickness,
    )
    return image.resize((size, size), Image.Resampling.LANCZOS)


class TrayController:
    def __init__(self, on_exit: Callable[[], None], on_export_diagnostics: Callable[[], None] | None = None, on_show_last_error: Callable[[], None] | None = None) -> None:
        self._on_exit = on_exit
        self._on_export_diagnostics = on_export_diagnostics
        self._on_show_last_error = on_show_last_error
        self._icon = None
        self._thread: threading.Thread | None = None
        self._status: ApplicationStatus = "idle"
        self._memory_active = False
        self._lock = threading.Lock()

    def start(self) -> None:
        import pystray

        def quit_app(icon, _item) -> None:
            icon.stop()
            self._on_exit()

        menu_items = []
        if self._on_show_last_error is not None:
            menu_items.extend((pystray.MenuItem("Show Last Error", lambda _icon, _item: self._on_show_last_error()), pystray.Menu.SEPARATOR))
        if self._on_export_diagnostics is not None:
            menu_items.extend(
                (
                    pystray.MenuItem("Export Diagnostics", lambda _icon, _item: self._on_export_diagnostics()),
                    pystray.Menu.SEPARATOR,
                )
            )
        menu_items.append(pystray.MenuItem("Quit ClipAI", quit_app))

        self._icon = pystray.Icon(
            "clipai",
            create_tray_image(self._status, memory_active=self._memory_active),
            "ClipAI",
            menu=pystray.Menu(*menu_items),
        )
        self._thread = threading.Thread(target=self._run, daemon=True, name="ClipAITray")
        self._thread.start()

    def _run(self) -> None:
        try:
            self._icon.run()
        except Exception:
            logger.exception("Tray icon loop failed")

    def set_status(self, status: ApplicationStatus) -> None:
        self._status = status
        self._update_icon()

    def set_memory_active(self, active: bool) -> None:
        self._memory_active = active
        self._update_icon()

    def _update_icon(self) -> None:
        if self._icon is None:
            return
        with self._lock:
            try:
                self._icon.icon = create_tray_image(self._status, memory_active=self._memory_active)
            except OSError:
                try:
                    time.sleep(0.05)
                    self._icon.icon = create_tray_image(self._status, memory_active=self._memory_active)
                except Exception:
                    logger.exception("Tray icon update failed after retry")
            except Exception:
                logger.exception("Tray icon update failed")

    def stop(self) -> None:
        if self._icon is not None:
            self._icon.stop()
            self._icon = None
        self._thread = None
