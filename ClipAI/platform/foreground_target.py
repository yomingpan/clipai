from __future__ import annotations

import ctypes
import sys

from ClipAI.core.models import ForegroundTarget


class WindowsForegroundTargetReader:
    """Reads the current top-level Windows target without affecting focus."""

    def current(self) -> ForegroundTarget | None:
        if sys.platform != "win32":
            return None
        try:
            hwnd = int(ctypes.windll.user32.GetForegroundWindow())
        except (AttributeError, OSError):
            return None
        return ForegroundTarget(hwnd) if hwnd else None
