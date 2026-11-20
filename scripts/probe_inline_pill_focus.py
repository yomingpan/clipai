"""Attended external-app probe. Click a blank target field, then each Pill button.

Never types, reads document content, sends Paste, or saves screen pixels. The
Pill emits only a local callback; native handles remain in memory.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import time
import tkinter as tk

from ClipAI.platform.display import WindowsDisplayMetricsReader
from ClipAI.platform.native_window import WindowsNativeWindowSurface
from ClipAI.ui.raster_resources import TkRasterResources


def focus_result(app, intent, before, shown, clicked, received):
    record = {
        "schema": 1, "app": app, "intent": intent,
        "foreground_kept_on_show": bool(before[0]) and shown[0] == before[0],
        "foreground_kept_on_click": bool(before[0]) and clicked[0] == before[0],
        "focused_control_kept": bool(before[1]) and shown[1] == clicked[1] == before[1],
        "intent_received": received is (intent == "refine"),
        "content_recorded": False,
    }
    record["status"] = "pass" if all(record[key] for key in ("foreground_kept_on_show", "foreground_kept_on_click", "focused_control_kept", "intent_received")) else "fail"
    return record


class _GUIThreadInfo(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("flags", wintypes.DWORD)] + [(name, wintypes.HWND) for name in ("active", "focus", "capture", "menu", "move", "caret")] + [("caret_rect", wintypes.RECT)]


def _native_observers():
    user, kernel = ctypes.windll.user32, ctypes.windll.kernel32
    user.GetForegroundWindow.restype = wintypes.HWND
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(_GUIThreadInfo)]
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    def observe():
        foreground = user.GetForegroundWindow()
        pid = wintypes.DWORD()
        thread = user.GetWindowThreadProcessId(foreground, ctypes.byref(pid))
        info = _GUIThreadInfo(size=ctypes.sizeof(_GUIThreadInfo))
        focused = info.focus if user.GetGUIThreadInfo(thread, ctypes.byref(info)) else 0
        process = kernel.OpenProcess(0x1000, False, pid.value)
        executable = ""
        if process:
            try:
                length = wintypes.DWORD(32768)
                path = ctypes.create_unicode_buffer(length.value)
                if kernel.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(length)):
                    executable = Path(path.value).name.lower()
            finally:
                kernel.CloseHandle(process)
        return executable, (foreground, focused)
    return observe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=300)
    args = parser.parse_args()
    from ClipAI.ui.inline_pill import InlinePill
    metrics = WindowsDisplayMetricsReader()
    root = tk.Tk()
    root.withdraw()
    raster_resources = TkRasterResources(root)
    native = WindowsNativeWindowSurface()
    observe = _native_observers()
    records = []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        for app, executable in (("Notepad", "notepad.exe"), ("Word", "winword.exe"), ("Edge", "msedge.exe")):
            for intent in ("raw", "refine"):
                print(json.dumps({"ready": app, "click": "check" if intent == "raw" else "sparkle"}), flush=True)
                deadline, stable, previous = time.monotonic()+args.timeout_seconds, None, None
                while time.monotonic() < deadline:
                    root.update()
                    name, current = observe()
                    if name == executable and current[1] and current == previous:
                        stable = stable or time.monotonic()
                        if time.monotonic()-stable >= 2:
                            break
                    else:
                        stable = None
                    previous = current
                    time.sleep(.03)
                else:
                    record = {"schema": 1, "app": app, "intent": intent, "status": "blocked", "reason": "external_target_not_ready", "content_recorded": False}
                    records.append(record)
                    break
                before = current
                received = []
                window = InlinePill(root, interaction_id=f"focus-{app}-{intent}", on_confirm=received.append, on_cancel=lambda: None, native_window_surface=native, display_metrics=metrics)
                try:
                    window.show()
                    root.update()
                    shown = observe()[1]
                    while not received and time.monotonic() < deadline:
                        root.update()
                        time.sleep(.01)
                    if received:
                        root.update()
                        record = focus_result(app, intent, before, shown, observe()[1], received[0])
                    else:
                        record = {"schema": 1, "app": app, "intent": intent, "status": "blocked", "reason": "click_timeout", "content_recorded": False}
                    records.append(record)
                finally:
                    window.close()
                    root.update()
                print(json.dumps(record), flush=True)
                # Give the operator time to release the mouse before the next case.
                time.sleep(.5)
    finally:
        raster_resources.close()
        root.destroy()
        with args.output.open("w", encoding="utf-8") as output:
            for record in records:
                output.write(json.dumps(record)+"\n")
    return 0 if len(records) == 6 and all(row["status"] == "pass" for row in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
