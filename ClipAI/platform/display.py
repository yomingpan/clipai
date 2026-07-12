from __future__ import annotations

import ctypes
from ctypes import wintypes

from ClipAI.core.models import DisplayMetrics


class WindowsDisplayMetricsReader:
    def __init__(self) -> None:
        self._declare_dpi_awareness()

    def current(self) -> DisplayMetrics:
        point = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
        monitor = ctypes.windll.user32.MonitorFromPoint(point, 2)
        info = _MonitorInfo()
        info.cbSize = ctypes.sizeof(info)
        ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(info))
        dpi_x = wintypes.UINT(96)
        dpi_y = wintypes.UINT(96)
        try:
            ctypes.windll.shcore.GetDpiForMonitor(monitor, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
        except (AttributeError, OSError):
            pass
        work = info.rcWork
        return DisplayMetrics(
            max(dpi_x.value / 96.0, 0.5),
            work.left,
            work.top,
            work.right - work.left,
            work.bottom - work.top,
            point.x,
            point.y,
        )

    @staticmethod
    def _declare_dpi_awareness() -> None:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except (AttributeError, OSError):
                pass


class _MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]
