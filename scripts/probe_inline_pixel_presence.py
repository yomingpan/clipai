"""Observe a controlled Inline window on the real desktop without saving pixels.

The probe samples an 8x8 patch of the window's known background after the
production Tk surface is shown. Latency is an observer upper bound, not the
exact first-pixel time or physical shortcut response.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import time
import tkinter as tk

from PIL import ImageGrab

from ClipAI.platform.display import WindowsDisplayMetricsReader
from ClipAI.platform.native_window import WindowsNativeWindowSurface
from ClipAI.support.statistics import percentile
from ClipAI.ui.inline_dictation import InlineDictationWindow, _clamp_inline_position


BACKGROUND = (32, 39, 43)
PATCH_SIZE = 8
PRESENCE_PIXELS = 56
AMBIGUOUS_PIXELS = 16


class ScreenCaptureUnavailable(RuntimeError):
    pass


class FixedCursorMetricsReader:
    def __init__(self, source: WindowsDisplayMetricsReader) -> None:
        self._source = source

    def current(self):
        metrics = self._source.current()
        return replace(
            metrics,
            cursor_x=metrics.work_x + min(100, metrics.work_width // 4),
            cursor_y=metrics.work_y + min(100, metrics.work_height // 4),
        )


def _background_pixels(x: int, y: int) -> int:
    try:
        image = ImageGrab.grab(bbox=(x + 2, y + 2, x + 2 + PATCH_SIZE, y + 2 + PATCH_SIZE))
    except OSError as error:
        raise ScreenCaptureUnavailable from error
    return sum(tuple(pixel[:3]) == BACKGROUND for pixel in image.getdata())


def _summary(values: list[float]) -> dict[str, float | int]:
    return {
        "count": len(values),
        "median_ms": round(statistics.median(values), 3),
        "p95_ms": round(percentile(values, .95), 3),
        "max_ms": round(max(values), 3),
    }


def _verdict(expected: int, observed: int, failures: list[dict[str, object]]) -> str:
    if observed == expected and not failures:
        return "pass"
    if failures and all(item["reason"] == "background_ambiguous" for item in failures):
        return "blocked"
    return "fail"


def measure(iterations: int, timeout_seconds: float) -> dict[str, object]:
    if iterations < 1 or timeout_seconds <= 0:
        raise ValueError("iterations and timeout must be positive")
    metrics = FixedCursorMetricsReader(WindowsDisplayMetricsReader())
    native = WindowsNativeWindowSurface()
    root = tk.Tk()
    root.withdraw()
    durations: dict[str, list[float]] = {"minimal": [], "choice": []}
    grab_durations: list[float] = []
    observed_samples: list[int] = []
    failures: list[dict[str, object]] = []
    try:
        for mode in ("minimal", "choice"):
            for iteration in range(iterations):
                window = InlineDictationWindow(
                    root, mode=mode, interaction_id=f"pixel-probe-{mode}-{iteration}",
                    on_confirm=lambda _refine: None, on_cancel=lambda: None,
                    native_window_surface=native, display_metrics=metrics,
                )
                try:
                    window._place()
                    x, y = _clamp_inline_position(
                        metrics.current(),
                        window._window.winfo_reqwidth(),
                        window._window.winfo_reqheight(),
                    )
                    before = _background_pixels(x, y)
                    if before > AMBIGUOUS_PIXELS:
                        failures.append({"mode": mode, "iteration": iteration, "reason": "background_ambiguous"})
                        continue
                    started = time.perf_counter()
                    window.show()
                    root.update()
                    actual_position = (window._window.winfo_rootx(), window._window.winfo_rooty())
                    if actual_position != (x, y):
                        failures.append({"mode": mode, "iteration": iteration, "reason": "position_mismatch"})
                        continue
                    samples = 0
                    max_matches = 0
                    while time.perf_counter() - started < timeout_seconds:
                        root.update()
                        samples += 1
                        grab_started = time.perf_counter()
                        matches = _background_pixels(x, y)
                        grab_durations.append((time.perf_counter() - grab_started) * 1000)
                        max_matches = max(max_matches, matches)
                        if matches >= PRESENCE_PIXELS:
                            durations[mode].append((time.perf_counter() - started) * 1000)
                            observed_samples.append(samples)
                            break
                    else:
                        failures.append({
                            "mode": mode, "iteration": iteration, "reason": "pixel_not_observed",
                            "samples": samples, "max_background_pixels": max_matches,
                            "position_before": [x, y],
                            "position_after": [window._window.winfo_rootx(), window._window.winfo_rooty()],
                            "viewable": bool(window._window.winfo_viewable()),
                        })
                finally:
                    window.close()
                    root.update()
    finally:
        root.destroy()
    expected = iterations * 2
    observed = sum(map(len, durations.values()))
    return {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "controlled_inline_onscreen_pixel_presence",
        "status": _verdict(expected, observed, failures),
        "iterations_per_mode": iterations,
        "observed_runs": observed,
        "pixel_presence_upper_bound_ms": {
            mode: _summary(values) if values else None for mode, values in durations.items()
        },
        "screen_grab_ms": _summary(grab_durations) if grab_durations else None,
        "samples_until_observed": {
            "min": min(observed_samples), "median": statistics.median(observed_samples),
            "max": max(observed_samples),
        } if observed_samples else None,
        "failures": failures,
        "pixel_data_saved": False,
        "limits": "8x8 background patch only; fixed controlled window position; screen-capture sampling delay included; no physical HID, microphone, Provider, Paste, or target insertion.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--timeout-seconds", type=float, default=0.5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = measure(args.iterations, args.timeout_seconds)
    except ScreenCaptureUnavailable:
        report = {
            "schema_version": 1,
            "scope": "controlled_inline_onscreen_pixel_presence",
            "status": "blocked",
            "reason": "screen_capture_unavailable",
            "observed_runs": 0,
            "pixel_data_saved": False,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "observed_runs": report["observed_runs"], "output": str(args.output)}))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
