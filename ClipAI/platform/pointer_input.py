from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Any


class WindowsPointerPressReader:
    """Report one screen-coordinate sample for each native mouse-button press."""

    _BUTTONS = (0x01, 0x02, 0x04)

    def __init__(self, user32: Any | None = None) -> None:
        self._user32 = user32 or ctypes.windll.user32
        self._down = {button: False for button in self._BUTTONS}

    def poll(self) -> tuple[int, int] | None:
        pressed = False
        try:
            for button in self._BUTTONS:
                state = int(self._user32.GetAsyncKeyState(button)) & 0xFFFF
                down = bool(state & 0x8000)
                pressed = pressed or bool(state & 0x0001) or (down and not self._down[button])
                self._down[button] = down
            if not pressed:
                return None
            point = wintypes.POINT()
            if not self._user32.GetCursorPos(ctypes.byref(point)):
                return None
            return int(point.x), int(point.y)
        except (AttributeError, OSError, TypeError, ValueError):
            return None


class HeadlessPointerPressReader:
    def poll(self) -> tuple[int, int] | None:
        return None
