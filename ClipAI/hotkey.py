from __future__ import annotations


class HotkeyListener:
    def __init__(self, on_trigger) -> None:
        self._on_trigger = on_trigger

    def trigger(self) -> None:
        self._on_trigger()
