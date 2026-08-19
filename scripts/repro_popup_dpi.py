from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass


@dataclass(frozen=True)
class Monitor:
    handle: int
    primary: bool
    left: int
    top: int
    right: int
    bottom: int
    dpi: int


class _MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def enum_display_monitors() -> list[Monitor]:
    user32 = ctypes.windll.user32
    shcore = ctypes.windll.shcore
    try:
        shcore.SetProcessDpiAwareness(2)
    except OSError:
        pass
    monitors: list[Monitor] = []
    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(wintypes.RECT),
        wintypes.LPARAM,
    )

    def visit(monitor, _hdc, _rect, _data) -> bool:
        info = _MonitorInfo()
        info.cbSize = ctypes.sizeof(info)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            raise ctypes.WinError()
        dpi_x = wintypes.UINT()
        dpi_y = wintypes.UINT()
        result = shcore.GetDpiForMonitor(
            monitor,
            0,
            ctypes.byref(dpi_x),
            ctypes.byref(dpi_y),
        )
        if result != 0:
            raise ctypes.WinError(result)
        work = info.rcWork
        monitors.append(
            Monitor(
                int(monitor),
                bool(info.dwFlags & 1),
                work.left,
                work.top,
                work.right,
                work.bottom,
                dpi_x.value,
            )
        )
        return True

    callback = callback_type(visit)
    if not user32.EnumDisplayMonitors(None, None, callback, 0):
        raise ctypes.WinError()
    return monitors


def main() -> int:
    monitors = enum_display_monitors()
    for monitor in monitors:
        print(
            f"primary={monitor.primary} work="
            f"({monitor.left},{monitor.top},{monitor.right},{monitor.bottom}) "
            f"dpi={monitor.dpi} scale={monitor.dpi / 96:.2f}"
        )

    from customtkinter.windows.widgets.scaling.scaling_tracker import ScalingTracker

    from ClipAI.ui.base_dialog import BaseDialog

    mismatches = 0
    for monitor in monitors:
        results = []
        foreground_before = ctypes.windll.user32.GetForegroundWindow()
        dialog = BaseDialog(
            title="ClipAI DPI repro",
            width=400,
            height=336,
            x=monitor.left + 100,
            y=monitor.top + 100,
        )
        for trial in range(30):
            if trial:
                dialog.root.withdraw()
                foreground_before = ctypes.windll.user32.GetForegroundWindow()
                dialog.root.deiconify()
            dialog.root.update_idletasks()
            cached = ScalingTracker.window_dpi_scaling_dict[dialog.root]
            truth = ScalingTracker.get_window_dpi_scaling(dialog.root)
            result = (
                cached == truth,
                ctypes.windll.user32.GetForegroundWindow() == foreground_before,
                bool(dialog.root.attributes("-topmost")),
                bool(dialog.root.winfo_viewable()),
            )
            results.append(result)
        dialog.close()
        print(
            f"target=({monitor.left + 100},{monitor.top + 100}) "
            f"cached==truth={sum(row[0] for row in results)}/30 "
            f"foreground_kept={sum(row[1] for row in results)}/30 "
            f"topmost={sum(row[2] for row in results)}/30 "
            f"visible={sum(row[3] for row in results)}/30"
        )
        mismatches += sum(not all(result) for result in results)

    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
