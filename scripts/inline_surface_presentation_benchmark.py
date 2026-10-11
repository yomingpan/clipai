"""Measure real Inline window presentation through the Windows compositor.

This exercises the production Tk surface on an interactive desktop. It does
not start a microphone, dispatch Paste, synthesize a shortcut, or observe pixels.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import statistics
import time
import tkinter as tk

from ClipAI.platform.display import WindowsDisplayMetricsReader
from ClipAI.platform.native_window import WindowsNativeWindowSurface
from ClipAI.support.statistics import percentile
from ClipAI.ui.inline_dictation import InlineDictationWindow
if __package__:
    from .popup_first_frame_benchmark import _await_presented_frame
else:
    from popup_first_frame_benchmark import _await_presented_frame


def _summary(values: list[float]) -> dict[str, float | int]:
    return {
        "count": len(values),
        "median_ms": round(statistics.median(values), 3),
        "p95_ms": round(percentile(values, .95), 3),
        "max_ms": round(max(values), 3),
    }


def _within_work_area(window: tk.Toplevel, reader: WindowsDisplayMetricsReader) -> bool:
    metrics = reader.current()
    return (
        window.winfo_rootx() >= metrics.work_x
        and window.winfo_rooty() >= metrics.work_y
        and window.winfo_rootx() + window.winfo_width() <= metrics.work_x + metrics.work_width
        and window.winfo_rooty() + window.winfo_height() <= metrics.work_y + metrics.work_height
    )


def measure(iterations: int) -> dict[str, object]:
    if iterations < 1:
        raise ValueError("iterations must be positive")
    reader = WindowsDisplayMetricsReader()
    native = WindowsNativeWindowSurface()
    root = tk.Tk()
    root.withdraw()
    display = reader.current()
    tcl_patchlevel = str(root.tk.call("info", "patchlevel"))
    timings: dict[str, list[float]] = {
        f"{mode}.{phase}": []
        for mode in ("minimal", "choice")
        for phase in ("initial", "refining", "recovery")
    }
    timings["choice.selection"] = []
    bounds_checks = 0
    bounds_failures = 0
    try:
        for mode in ("minimal", "choice"):
            for iteration in range(iterations):
                started = time.perf_counter()
                window = InlineDictationWindow(
                    root, mode=mode, interaction_id=f"benchmark-{mode}-{iteration}",
                    on_confirm=lambda _refine: None, on_cancel=lambda: None,
                    native_window_surface=native, display_metrics=reader,
                )
                try:
                    window.show()
                    _await_presented_frame(window._window)
                    timings[f"{mode}.initial"].append((time.perf_counter() - started) * 1000)
                    if mode == "choice":
                        started = time.perf_counter()
                        window.present_choice("受控測試文字。" * 12)
                        _await_presented_frame(window._window)
                        timings["choice.selection"].append((time.perf_counter() - started) * 1000)
                        bounds_checks += 1
                        bounds_failures += not _within_work_area(window._window, reader)

                    started = time.perf_counter()
                    window.show_refining()
                    _await_presented_frame(window._window)
                    timings[f"{mode}.refining"].append((time.perf_counter() - started) * 1000)

                    started = time.perf_counter()
                    window.show_recovery("受控測試文字。" * 12, "潤稿未完成，原文仍可使用。")
                    _await_presented_frame(window._window)
                    timings[f"{mode}.recovery"].append((time.perf_counter() - started) * 1000)
                    bounds_checks += 1
                    bounds_failures += not _within_work_area(window._window, reader)
                finally:
                    window.close()
                    root.update_idletasks()
    finally:
        root.destroy()
    return {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "inline_tk_to_dwm_settlement",
        "device_class": {
            "os_build": platform.win32_ver()[1],
            "logical_processors": os.cpu_count(),
            "work_area_pixels": [display.work_width, display.work_height],
            "dpi_scale": round(display.scale, 2),
            "tcl_patchlevel": tcl_patchlevel,
        },
        "iterations_per_mode": iterations,
        "status": "pass" if bounds_failures == 0 else "fail",
        "phase_ms": {name: _summary(values) for name, values in timings.items()},
        "work_area_bounds_checks": bounds_checks,
        "work_area_bounds_failures": bounds_failures,
        "content_recorded": False,
        "limits": "Tk show/update_idletasks to DwmFlush; no pixel observer, physical HID, microphone, Provider, Paste, or target insertion.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = measure(args.iterations)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(args.output)}))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
