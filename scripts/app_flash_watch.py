from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import time
from ctypes import wintypes
from dataclasses import asdict, dataclass


GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
LWA_ALPHA = 0x00000002


@dataclass(frozen=True)
class VisibleWindowSample:
    elapsed_ms: int
    hwnd: int
    title: str
    rect: tuple[int, int, int, int]
    ex_style: int
    alpha: int | None

    @property
    def opaque(self) -> bool:
        return self.alpha is None or self.alpha > 0


def _configure_user32(user32: object) -> None:
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32._clipai_enum_callback = callback  # type: ignore[attr-defined]
    user32.EnumWindows.argtypes = [callback, wintypes.LPARAM]  # type: ignore[attr-defined]
    user32.EnumWindows.restype = wintypes.BOOL  # type: ignore[attr-defined]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]  # type: ignore[attr-defined]
    user32.IsWindowVisible.restype = wintypes.BOOL  # type: ignore[attr-defined]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]  # type: ignore[attr-defined]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD  # type: ignore[attr-defined]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]  # type: ignore[attr-defined]
    user32.GetWindowTextLengthW.restype = ctypes.c_int  # type: ignore[attr-defined]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]  # type: ignore[attr-defined]
    user32.GetWindowTextW.restype = ctypes.c_int  # type: ignore[attr-defined]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]  # type: ignore[attr-defined]
    user32.GetWindowRect.restype = wintypes.BOOL  # type: ignore[attr-defined]
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]  # type: ignore[attr-defined]
    user32.GetWindowLongW.restype = ctypes.c_long  # type: ignore[attr-defined]
    user32.GetLayeredWindowAttributes.argtypes = [  # type: ignore[attr-defined]
        wintypes.HWND,
        ctypes.POINTER(wintypes.COLORREF),
        ctypes.POINTER(wintypes.BYTE),
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetLayeredWindowAttributes.restype = wintypes.BOOL  # type: ignore[attr-defined]


def visible_windows_for_process(pid: int, *, elapsed_ms: int, user32: object) -> list[VisibleWindowSample]:
    samples: list[VisibleWindowSample] = []

    def visit(hwnd: int, _lparam: int) -> bool:
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))  # type: ignore[attr-defined]
        if owner.value != pid or not user32.IsWindowVisible(hwnd):  # type: ignore[attr-defined]
            return True
        title_length = user32.GetWindowTextLengthW(hwnd)  # type: ignore[attr-defined]
        title_buffer = ctypes.create_unicode_buffer(title_length + 1)
        user32.GetWindowTextW(hwnd, title_buffer, len(title_buffer))  # type: ignore[attr-defined]
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))  # type: ignore[attr-defined]
        ex_style = int(user32.GetWindowLongW(hwnd, GWL_EXSTYLE))  # type: ignore[attr-defined]
        alpha: int | None = None
        if ex_style & WS_EX_LAYERED:
            color_key = wintypes.COLORREF()
            alpha_value = wintypes.BYTE()
            flags = wintypes.DWORD()
            if user32.GetLayeredWindowAttributes(  # type: ignore[attr-defined]
                hwnd,
                ctypes.byref(color_key),
                ctypes.byref(alpha_value),
                ctypes.byref(flags),
            ) and flags.value & LWA_ALPHA:
                alpha = int(alpha_value.value)
        samples.append(VisibleWindowSample(
            elapsed_ms=elapsed_ms,
            hwnd=int(hwnd),
            title=title_buffer.value,
            rect=(rect.left, rect.top, rect.right, rect.bottom),
            ex_style=ex_style,
            alpha=alpha,
        ))
        return True

    callback = user32._clipai_enum_callback(visit)  # type: ignore[attr-defined]
    if not user32.EnumWindows(callback, 0):  # type: ignore[attr-defined]
        raise ctypes.WinError()
    return samples


def watch(pid: int, *, interval_ms: int, duration_seconds: float) -> int:
    if sys.platform != "win32":
        raise RuntimeError("app_flash_watch.py requires Windows")
    user32 = ctypes.windll.user32
    _configure_user32(user32)
    started = time.perf_counter()
    deadline = started + duration_seconds
    sample_count = 0
    opaque_frames = 0
    visible_frames = 0
    while time.perf_counter() < deadline:
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        windows = visible_windows_for_process(pid, elapsed_ms=elapsed_ms, user32=user32)
        sample_count += 1
        visible_frames += int(bool(windows))
        opaque_frames += int(any(sample.opaque for sample in windows))
        print(json.dumps({"sample": sample_count, "windows": [asdict(sample) for sample in windows]}), flush=True)
        next_sample = started + (sample_count * interval_ms / 1000)
        time.sleep(max(0.0, next_sample - time.perf_counter()))
    print(json.dumps({
        "pid": pid,
        "interval_ms": interval_ms,
        "samples": sample_count,
        "visible_frames": visible_frames,
        "opaque_frames": opaque_frames,
    }), flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Sample every visible top-level window owned by one process.")
    parser.add_argument("--pid", type=int, required=True, help="Process id to inspect")
    parser.add_argument("--interval-ms", type=int, default=20, help="Sampling interval (default: 20 ms)")
    parser.add_argument("--duration-seconds", type=float, default=5.0, help="Observation duration")
    args = parser.parse_args()
    if args.pid <= 0 or args.interval_ms <= 0 or args.duration_seconds <= 0:
        parser.error("pid, interval, and duration must be positive")
    if args.pid == os.getpid():
        parser.error("watch a separate target process")
    return watch(args.pid, interval_ms=args.interval_ms, duration_seconds=args.duration_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
