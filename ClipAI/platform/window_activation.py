from __future__ import annotations

from typing import Any


def activate_top_level_window(
    window_handle: int,
    *,
    user32: Any,
    kernel32: Any,
) -> bool:
    """Activate one exact top-level HWND through the caller's input queue."""

    current_thread = 0
    attached_threads: list[int] = []
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
