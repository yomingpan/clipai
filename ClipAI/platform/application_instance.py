from __future__ import annotations

from collections.abc import Callable
import threading
from typing import Any


ERROR_ALREADY_EXISTS = 183


class _WindowsApplicationInstanceLease:
    def __init__(self, handle: int, close_handle: Callable[[int], Any]) -> None:
        self._handle = handle
        self._close_handle = close_handle
        self._lock = threading.Lock()

    def close(self) -> None:
        with self._lock:
            handle, self._handle = self._handle, 0
        if handle:
            self._close_handle(handle)


class WindowsApplicationInstanceGate:
    """Admit one ClipAI desktop runtime in the current Windows session."""

    def __init__(
        self,
        name: str,
        *,
        create_mutex: Callable[[object | None, bool, str], int] | None = None,
        get_last_error: Callable[[], int] | None = None,
        close_handle: Callable[[int], Any] | None = None,
    ) -> None:
        if not name.strip():
            raise ValueError("Application instance mutex name must not be empty")
        if create_mutex is None or get_last_error is None or close_handle is None:
            create_mutex, get_last_error, close_handle = _windows_mutex_functions()
        self._name = name
        self._create_mutex = create_mutex
        self._get_last_error = get_last_error
        self._close_handle = close_handle

    def acquire(self) -> _WindowsApplicationInstanceLease | None:
        handle = int(self._create_mutex(None, False, self._name) or 0)
        error = int(self._get_last_error())
        if not handle:
            raise OSError(error, "Unable to create the ClipAI application-instance mutex")
        if error == ERROR_ALREADY_EXISTS:
            self._close_handle(handle)
            return None
        return _WindowsApplicationInstanceLease(handle, self._close_handle)


def _windows_mutex_functions() -> tuple[
    Callable[[object | None, bool, str], int],
    Callable[[], int],
    Callable[[int], Any],
]:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_mutex = kernel32.CreateMutexW
    create_mutex.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    create_mutex.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    return create_mutex, ctypes.get_last_error, close_handle
