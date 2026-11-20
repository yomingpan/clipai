from __future__ import annotations

import ctypes
from typing import Any

from ClipAI.platform.win32_api import configure_win32_api


SPI_GETFOREGROUNDLOCKTIMEOUT = 0x2000
SPI_SETFOREGROUNDLOCKTIMEOUT = 0x2001
SPIF_SENDCHANGE = 0x0002


def _suspend_foreground_lock_timeout(user32: Any) -> int | None:
    try:
        previous = ctypes.c_uint32()
        if not user32.SystemParametersInfoW(
            SPI_GETFOREGROUNDLOCKTIMEOUT, 0, ctypes.byref(previous), 0
        ):
            return None
        if not user32.SystemParametersInfoW(
            SPI_SETFOREGROUNDLOCKTIMEOUT, 0, ctypes.c_void_p(0), SPIF_SENDCHANGE
        ):
            return None
        return int(previous.value)
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def _restore_foreground_lock_timeout(user32: Any, previous: int | None) -> None:
    if previous is None:
        return
    try:
        user32.SystemParametersInfoW(
            SPI_SETFOREGROUNDLOCKTIMEOUT,
            0,
            ctypes.c_void_p(int(previous)),
            SPIF_SENDCHANGE,
        )
    except (AttributeError, OSError, TypeError, ValueError):
        pass


def activate_top_level_window(
    window_handle: int,
    *,
    user32: Any,
    kernel32: Any,
) -> bool:
    """Activate one exact top-level HWND through the caller's input queue."""

    configure_win32_api(user32, kernel32)

    current_thread = 0
    attached_threads: list[int] = []
    previous_lock_timeout = _suspend_foreground_lock_timeout(user32)
    try:
        foreground = int(user32.GetForegroundWindow())
        current_thread = int(kernel32.GetCurrentThreadId())
        related_threads: list[int] = []
        for handle in (foreground, window_handle):
            if not handle:
                continue
            thread_id = int(user32.GetWindowThreadProcessId(handle, None))
            if (
                thread_id
                and thread_id != current_thread
                and thread_id not in related_threads
            ):
                related_threads.append(thread_id)
        for thread_id in related_threads:
            if user32.AttachThreadInput(current_thread, thread_id, True):
                attached_threads.append(thread_id)
        user32.BringWindowToTop(window_handle)
        user32.SetForegroundWindow(window_handle)
        user32.SetActiveWindow(window_handle)
        return int(user32.GetForegroundWindow()) == window_handle
    except (AttributeError, OSError, TypeError, ValueError):
        return False
    finally:
        for thread_id in reversed(attached_threads):
            try:
                user32.AttachThreadInput(current_thread, thread_id, False)
            except (AttributeError, OSError, TypeError, ValueError):
                pass
        _restore_foreground_lock_timeout(user32, previous_lock_timeout)
