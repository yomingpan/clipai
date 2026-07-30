from __future__ import annotations

from collections.abc import Callable
import ctypes
from pathlib import Path
import os
import threading

from ClipAI.core.models import PasteTarget


EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT = 0x0000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class WindowsForegroundWindowMonitor:
    """Observe Windows foreground changes without driving application policy."""

    def __init__(
        self,
        callback: Callable[[PasteTarget], None],
        *,
        user32=None,
        read_target: Callable[[int, int], tuple[int, str, str] | None] | None = None,
        process_id: int | None = None,
        callback_factory=None,
    ) -> None:
        self._callback = callback
        self._user32 = user32 or ctypes.windll.user32
        self._read_target = read_target or _read_windows_target
        self._process_id = os.getpid() if process_id is None else process_id
        self._callback_factory = callback_factory or ctypes.WINFUNCTYPE(
            None,
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_void_p,
            ctypes.c_long,
            ctypes.c_long,
            ctypes.c_ulong,
            ctypes.c_ulong,
        )
        self._hook = None
        self._callback_ref = None
        self._sequence = 0
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._hook is not None:
            return
        self._callback_ref = self._callback_factory(self._on_foreground_event)
        hook = self._user32.SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND,
            EVENT_SYSTEM_FOREGROUND,
            0,
            self._callback_ref,
            0,
            0,
            WINEVENT_OUTOFCONTEXT,
        )
        if not hook:
            self._callback_ref = None
            raise OSError("Could not monitor the Windows foreground window.")
        self._hook = hook
        try:
            current = int(self._user32.GetForegroundWindow())
        except (AttributeError, OSError, TypeError, ValueError):
            current = 0
        if current:
            self._observe(current)

    def stop(self) -> None:
        hook = self._hook
        self._hook = None
        if hook is not None:
            try:
                self._user32.UnhookWinEvent(hook)
            except (AttributeError, OSError, TypeError, ValueError):
                pass
        self._callback_ref = None

    def _on_foreground_event(
        self,
        _hook,
        _event,
        window,
        _object_id,
        _child_id,
        _event_thread,
        _event_time,
    ) -> None:
        try:
            handle = int(window or 0)
        except (TypeError, ValueError):
            return
        if handle:
            self._observe(handle)

    def _observe(self, handle: int) -> None:
        details = self._read_target(handle, self._process_id)
        if details is None:
            return
        process_id, application_name, window_title = details
        with self._lock:
            self._sequence += 1
            sequence = self._sequence
        self._callback(
            PasteTarget(
                window_token=f"hwnd:{handle:x}",
                process_id=process_id,
                application_name=application_name,
                window_title=window_title,
                observation_sequence=sequence,
            )
        )


def _read_windows_target(handle: int, own_process_id: int) -> tuple[int, str, str] | None:
    user32 = ctypes.windll.user32
    process_id = ctypes.c_ulong()
    try:
        if not user32.IsWindow(handle) or not user32.IsWindowVisible(handle):
            return None
        if not user32.GetWindowThreadProcessId(handle, ctypes.byref(process_id)):
            return None
    except (AttributeError, OSError, TypeError, ValueError):
        return None
    if not process_id.value or process_id.value == own_process_id:
        return None
    title = _window_title(user32, handle)
    application_name = _process_name(process_id.value)
    return process_id.value, application_name, title


def _window_title(user32, handle: int) -> str:
    try:
        length = max(0, int(user32.GetWindowTextLengthW(handle)))
        if not length:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(handle, buffer, len(buffer))
        return buffer.value.strip()
    except (AttributeError, OSError, TypeError, ValueError):
        return ""


def _process_name(process_id: int) -> str:
    kernel32 = ctypes.windll.kernel32
    handle = None
    try:
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id)
        if not handle:
            return "Windows app"
        size = ctypes.c_ulong(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return "Windows app"
        return Path(buffer.value).stem or "Windows app"
    except (AttributeError, OSError, TypeError, ValueError):
        return "Windows app"
    finally:
        if handle:
            try:
                kernel32.CloseHandle(handle)
            except (AttributeError, OSError, TypeError, ValueError):
                pass
