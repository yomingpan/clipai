from __future__ import annotations

import sys
from typing import Protocol


class PointerPressReader(Protocol):
    def poll(self) -> tuple[int, int] | None: ...


class WindowsPointerPressReader:
    """Report one screen-coordinate sample for each native mouse-button press."""

    _BUTTONS = (0x01, 0x02, 0x04)  # left, right, middle

    def __init__(self, user32=None) -> None:
        if user32 is None and sys.platform == "win32":
            import ctypes

            user32 = ctypes.windll.user32
        self._user32 = user32
        self._down = {button: False for button in self._BUTTONS}

    def poll(self) -> tuple[int, int] | None:
        user32 = self._user32
        if user32 is None:
            return None

        pressed = False
        try:
            for button in self._BUTTONS:
                state = int(user32.GetAsyncKeyState(button)) & 0xFFFF
                down = bool(state & 0x8000)
                pressed = pressed or bool(state & 0x0001) or (down and not self._down[button])
                self._down[button] = down
            if not pressed:
                return None

            import ctypes
            from ctypes import wintypes

            point = wintypes.POINT()
            if not user32.GetCursorPos(ctypes.byref(point)):
                return None
            return int(point.x), int(point.y)
        except (AttributeError, OSError, TypeError, ValueError):
            return None
