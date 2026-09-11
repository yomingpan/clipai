"""Interactive Windows benchmark for first frame and Entry Panel host reuse."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import time
import tkinter as tk

import customtkinter as ctk

from ClipAI.core.models import PopupBounds
from ClipAI.platform.native_window import WindowsNativeWindowSurface
from ClipAI.ui.primary_surface import PrimarySurfaceHost, PrimarySurfaceSpec


class _View:
    def __init__(self, host: PrimarySurfaceHost) -> None:
        self._frame = ctk.CTkFrame(host.window)

    def mount_primary_content(self) -> bool:
        self._frame.pack(fill="both", expand=True)
        return True

    def unmount_primary_content(self) -> None:
        self._frame.pack_forget()


def _percentile(values: list[float], fraction: float) -> float:
    values = sorted(values)
    return values[min(len(values) - 1, round((len(values) - 1) * fraction))]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("artifacts/popup-first-frame.jsonl"))
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--threshold-ms", type=float, default=150.0)
    args = parser.parse_args()
    root = tk.Tk()
    root.withdraw()
    first_frames: list[float] = []
    reclaims: list[float] = []
    try:
        for _ in range(args.iterations):
            started = time.perf_counter()
            host = PrimarySurfaceHost(
                root,
                PrimarySurfaceSpec(PopupBounds(80, 80, 400, 336)),
                WindowsNativeWindowSurface(),
            )
            panel_lease = host.acquire()
            panel = _View(host)
            host.mount(panel_lease, panel)
            host.apply_visibility("visible_no_activate")
            host.window.update_idletasks()
            first_frames.append((time.perf_counter() - started) * 1000)

            popup_lease = host.acquire()
            popup = _View(host)
            started = time.perf_counter()
            host.lifecycle.cancel_scheduled()
            host.replace(panel_lease, popup_lease, popup)
            host.window.update_idletasks()
            reclaims.append((time.perf_counter() - started) * 1000)
            host.close(popup_lease)
    finally:
        root.destroy()
    record = {
        "schema": 1,
        "gate": "popup-first-frame-live",
        "iterations": args.iterations,
        "first_frame_ms": {"p50": round(statistics.median(first_frames), 3), "p95": round(_percentile(first_frames, .95), 3)},
        "reclaim_ms": {"p50": round(statistics.median(reclaims), 3), "p95": round(_percentile(reclaims, .95), 3)},
        "threshold_ms": args.threshold_ms,
        "passed": _percentile(first_frames, .95) <= args.threshold_ms and _percentile(reclaims, .95) <= args.threshold_ms,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=True) + "\n")
    return 0 if record["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
