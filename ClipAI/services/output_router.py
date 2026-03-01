from __future__ import annotations

from typing import Callable


class OutputRouter:
    def __init__(
        self,
        show_popup: Callable[[str], None],
        copy_clipboard: Callable[[str], None],
        auto_paste: Callable[[str], None],
        notify: Callable[[str], None],
    ) -> None:
        self._show_popup = show_popup
        self._copy_clipboard = copy_clipboard
        self._auto_paste = auto_paste
        self._notify = notify

    def route(self, content: str, output_config: dict[str, bool]) -> None:
        if output_config.get("popup", True):
            self._show_popup(content)
        if output_config.get("clipboard"):
            self._copy_clipboard(content)
        if output_config.get("paste"):
            self._auto_paste(content)
        if output_config.get("notify"):
            self._notify(content)
