from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from ClipAI.core.models import ExternalWindowRef, SelectionCaptureOutcome, SelectionSource
from ClipAI.core.state import CancellationToken
from ClipAI.platform.win32_api import configure_win32_api


class _GuiThreadInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND), ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


def capture_windows_source(target: ExternalWindowRef | None = None) -> SelectionSource | None:
    if os.name != "nt":
        return None
    user32 = ctypes.windll.user32
    configure_win32_api(user32, ctypes.windll.kernel32)
    hwnd = user32.GetForegroundWindow()
    pid = wintypes.DWORD()
    thread = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not hwnd or not thread or pid.value == os.getpid():
        return None
    token = f"hwnd:{int(hwnd):x}"
    if target is not None and (target.window_token != token or target.process_id != pid.value):
        return None
    info = _GuiThreadInfo()
    info.cbSize = ctypes.sizeof(info)
    if not user32.GetGUIThreadInfo(thread, ctypes.byref(info)) or not info.hwndFocus:
        return None
    window = target or ExternalWindowRef(token, pid.value, 0)
    return SelectionSource(window, f"hwnd:{int(info.hwndFocus):x}")


class WindowsSelectionProbe:
    """Run potentially hung cross-process UIA providers in a disposable process."""

    def __init__(self, *, timeout_sec: float = 2.0, process_factory=subprocess.Popen) -> None:
        self._timeout_sec = timeout_sec
        self._process_factory = process_factory

    def capture_source(self, target: ExternalWindowRef | None) -> SelectionSource | None:
        return capture_windows_source(target)

    def source_is_current(self, source: SelectionSource) -> bool:
        return capture_windows_source(source.window) == source

    def probe(self, source: SelectionSource, cancellation: CancellationToken | None) -> SelectionCaptureOutcome:
        if cancellation is not None and cancellation.is_cancelled:
            return SelectionCaptureOutcome(status="cancelled", strategy="uia")
        request = json.dumps({
            "window_token": source.window.window_token,
            "process_id": source.window.process_id,
            "observation_sequence": source.window.observation_sequence,
            "focus_token": source.focus_token,
        })
        process = None
        try:
            process = self._process_factory(
                # Windows venv python.exe can be a redirector with a child process.
                # Launch the real interpreter so killing this PID kills the UIA call.
                [
                    getattr(sys, "_base_executable", sys.executable), "-c",
                    "import json,runpy,sys; sys.path[:]=json.loads(sys.argv[1]); "
                    "runpy.run_module('ClipAI.platform.selection_uia_worker',run_name='__main__')",
                    json.dumps([str(Path(__file__).resolve().parents[2])] + [str(Path(p).resolve()) for p in sys.path if p]),
                ],
                cwd=str(Path(__file__).resolve().parents[2]),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            deadline = time.monotonic() + self._timeout_sec
            first = True
            while True:
                if cancellation is not None and cancellation.is_cancelled:
                    return SelectionCaptureOutcome(status="cancelled", strategy="uia")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return SelectionCaptureOutcome(reason="uia_timeout", strategy="uia")
                try:
                    stdout, _stderr = process.communicate(request if first else None, timeout=min(0.05, remaining))
                    break
                except subprocess.TimeoutExpired:
                    first = False
            if process.returncode:
                return SelectionCaptureOutcome(reason="uia_worker_failed", strategy="uia")
            payload = json.loads(stdout)
            status = payload.get("status")
            if status not in {"selected", "none", "unknown"}:
                return SelectionCaptureOutcome(reason="uia_invalid_result", strategy="uia")
            return SelectionCaptureOutcome(
                text=payload.get("text", ""), status=status,
                reason=payload.get("reason", ""), strategy="uia",
                selection_detected=payload.get("selection_detected", False),
            )
        except Exception:
            return SelectionCaptureOutcome(reason="uia_unavailable", strategy="uia")
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                # Reap the helper and close all redirected handles, even on cancellation.
                try:
                    process.communicate(timeout=1)
                except (OSError, subprocess.TimeoutExpired):
                    pass
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream is not None:
                        stream.close()
