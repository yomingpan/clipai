"""Interactive Windows benchmark for production Entry and Popup first frames."""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import statistics
import time

import customtkinter as ctk

from ClipAI.core.models import (
    DisplayMetrics,
    EntryActionRef,
    EntryPanelOption,
    EntryPanelSnapshot,
    PopupBounds,
)
from ClipAI.platform.native_window import WindowsNativeWindowSurface
from ClipAI.support.statistics import percentile
from ClipAI.ui.base_dialog import BaseDialog, BaseResultSurface
from ClipAI.ui.primary_surface import PrimarySurfaceHost, PrimarySurfaceSpec
from ClipAI.ui.unified_entry_panel import UnifiedEntryPanelDialog


class _MetricsReader:
    def current(self) -> DisplayMetrics:
        return DisplayMetrics(1.0, 0, 0, 1920, 1080, 280, 240)


def _dwm_flush() -> None:
    if os.name != "nt":
        raise RuntimeError("popup first-frame benchmark requires Windows")
    dwmapi = ctypes.WinDLL("dwmapi")
    dwmapi.DwmFlush.argtypes = []
    dwmapi.DwmFlush.restype = ctypes.c_long
    result = int(dwmapi.DwmFlush())
    if result != 0:
        raise OSError(result, "DwmFlush failed")


def _await_presented_frame(window, *, flush=_dwm_flush) -> None:
    """Flush Tk layout/paint, then wait for Desktop Window Manager settlement."""
    window.update_idletasks()
    if not bool(window.winfo_viewable()):
        raise RuntimeError("primary surface did not become viewable")
    flush()


def _panel_snapshot(iteration: int) -> EntryPanelSnapshot:
    return EntryPanelSnapshot(
        f"benchmark-panel-{iteration}",
        "root",
        status="preparing",
        message="正在讀取來源內容…",
        options=(
            EntryPanelOption(
                0,
                "最近使用",
                "保留意思並縮短篇幅",
                action=EntryActionRef("shorten_content", "short"),
                pending=True,
            ),
        ),
    )


def _build_popup(root, host: PrimarySurfaceHost, lease) -> BaseDialog:
    dialog = BaseDialog(
        title="ClipAI",
        width=400,
        height=336,
        master=root,
        frameless=True,
        transparent_background=True,
        surface_color="#2B2B2B",
        primary_surface_host=host,
        primary_surface_lease=lease,
        mount_primary_content=False,
        show_on_create=False,
    )
    surface = BaseResultSurface(dialog)
    surface.set_title("縮短內容")
    surface.set_source_preview("正在處理選取內容")
    surface.set_model("benchmark")
    surface.set_loading()
    return dialog


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("artifacts/popup-first-frame.jsonl"))
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--threshold-ms", type=float, default=150.0)
    args = parser.parse_args()
    root = ctk.CTk()
    root.withdraw()
    first_frames: list[float] = []
    reclaims: list[float] = []
    host_builds: list[float] = []
    panel_builds: list[float] = []
    panel_presents: list[float] = []
    reclaim_mounts: list[float] = []
    reclaim_presents: list[float] = []
    native_surface = WindowsNativeWindowSurface()
    try:
        for iteration in range(args.iterations):
            started = time.perf_counter()
            host = PrimarySurfaceHost(
                root,
                PrimarySurfaceSpec(PopupBounds(80, 80, 400, 336)),
                native_surface,
            )
            host_built = time.perf_counter()
            panel_lease = host.acquire()
            panel = UnifiedEntryPanelDialog(
                root,
                lambda _command: None,
                native_surface,
                _MetricsReader(),
                primary_surface_host=host,
                primary_surface_lease=panel_lease,
            )
            panel.apply(_panel_snapshot(iteration))
            if not host.mount(panel_lease, panel):
                raise RuntimeError("production Entry Panel did not mount")
            panel_built = time.perf_counter()
            if not host.apply_visibility("visible_no_activate"):
                raise RuntimeError("production Entry Panel visibility request failed")
            _await_presented_frame(host.window)
            panel_presented = time.perf_counter()
            first_frames.append((panel_presented - started) * 1000)
            host_builds.append((host_built - started) * 1000)
            panel_builds.append((panel_built - host_built) * 1000)
            panel_presents.append((panel_presented - panel_built) * 1000)

            popup_lease = host.acquire()
            popup = _build_popup(root, host, popup_lease)
            panel.close()
            started = time.perf_counter()
            if not host.replace(panel_lease, popup_lease, popup):
                raise RuntimeError("production Entry-to-Popup reclaim failed")
            popup_mounted = time.perf_counter()
            _await_presented_frame(host.window)
            popup_presented = time.perf_counter()
            reclaims.append((popup_presented - started) * 1000)
            reclaim_mounts.append((popup_mounted - started) * 1000)
            reclaim_presents.append((popup_presented - popup_mounted) * 1000)
            host.close(popup_lease)
    finally:
        root.destroy()
    first_frame_p95 = percentile(first_frames, .95)
    reclaim_p95 = percentile(reclaims, .95)
    record = {
        "schema": 2,
        "gate": "popup-first-frame-live",
        "measurement": "production-surfaces+dwm-flush",
        "iterations": args.iterations,
        "visible_frames": args.iterations * 2,
        "first_frame_ms": {
            "p50": round(statistics.median(first_frames), 3),
            "p95": round(first_frame_p95, 3),
        },
        "reclaim_ms": {
            "p50": round(statistics.median(reclaims), 3),
            "p95": round(reclaim_p95, 3),
        },
        "phase_ms": {
            "host_build_p95": round(percentile(host_builds, .95), 3),
            "panel_build_p95": round(percentile(panel_builds, .95), 3),
            "panel_present_p95": round(percentile(panel_presents, .95), 3),
            "reclaim_mount_p95": round(percentile(reclaim_mounts, .95), 3),
            "reclaim_present_p95": round(percentile(reclaim_presents, .95), 3),
        },
        "threshold_ms": args.threshold_ms,
        "passed": first_frame_p95 <= args.threshold_ms and reclaim_p95 <= args.threshold_ms,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=True) + "\n")
    return 0 if record["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
