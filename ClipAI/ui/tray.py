from __future__ import annotations

from collections.abc import Callable


class TrayController:
    def __init__(self, on_exit: Callable[[], None]) -> None:
        self._on_exit = on_exit
        self._icon = None

    def start(self) -> None:
        import pystray
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (64, 64), "#111111")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((8, 8, 56, 56), radius=12, fill="#1F6AA5")
        draw.text((21, 18), "AI", fill="white")

        def quit_app(icon, _item) -> None:
            icon.stop()
            self._on_exit()

        self._icon = pystray.Icon(
            "clipai",
            image,
            "ClipAI",
            menu=pystray.Menu(pystray.MenuItem("Quit ClipAI", quit_app)),
        )
        self._icon.run_detached()

    def stop(self) -> None:
        if self._icon is not None:
            self._icon.stop()
            self._icon = None

