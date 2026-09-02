from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Any


_callback_factory = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
WinEventProc = _callback_factory(
    None,
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.HWND,
    wintypes.LONG,
    wintypes.LONG,
    wintypes.DWORD,
    wintypes.DWORD,
)


def configure_win32_api(user32: Any, kernel32: Any) -> None:
    """Declare the pointer-sized Win32 ABI used by ClipAI window adapters."""

    pointer_to_dword = ctypes.POINTER(wintypes.DWORD)
    declarations: tuple[tuple[Any, str, list[Any], Any], ...] = (
        (user32, "SetWinEventHook", [wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE, WinEventProc, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD], wintypes.HANDLE),
        (user32, "UnhookWinEvent", [wintypes.HANDLE], wintypes.BOOL),
        (user32, "GetForegroundWindow", [], wintypes.HWND),
        (user32, "GetWindowThreadProcessId", [wintypes.HWND, pointer_to_dword], wintypes.DWORD),
        (user32, "AttachThreadInput", [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL], wintypes.BOOL),
        (user32, "BringWindowToTop", [wintypes.HWND], wintypes.BOOL),
        (user32, "SetForegroundWindow", [wintypes.HWND], wintypes.BOOL),
        (user32, "SetActiveWindow", [wintypes.HWND], wintypes.HWND),
        (user32, "IsWindow", [wintypes.HWND], wintypes.BOOL),
        (user32, "IsWindowVisible", [wintypes.HWND], wintypes.BOOL),
        (user32, "GetWindowTextLengthW", [wintypes.HWND], ctypes.c_int),
        (user32, "GetWindowTextW", [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
        (user32, "GetParent", [wintypes.HWND], wintypes.HWND),
        (user32, "GetWindowLongW", [wintypes.HWND, ctypes.c_int], wintypes.LONG),
        (user32, "SetWindowLongW", [wintypes.HWND, ctypes.c_int, wintypes.LONG], wintypes.LONG),
        (user32, "SetWindowPos", [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT], wintypes.BOOL),
        (user32, "ShowWindow", [wintypes.HWND, ctypes.c_int], wintypes.BOOL),
        (user32, "LoadImageW", [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT], wintypes.HANDLE),
        (user32, "SendMessageW", [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM], wintypes.LPARAM),
        (user32, "DestroyIcon", [wintypes.HANDLE], wintypes.BOOL),
        (user32, "GetAsyncKeyState", [ctypes.c_int], wintypes.SHORT),
        (user32, "GetCursorPos", [ctypes.POINTER(wintypes.POINT)], wintypes.BOOL),
        (user32, "MonitorFromPoint", [wintypes.POINT, wintypes.DWORD], wintypes.HANDLE),
        (user32, "GetMonitorInfoW", [wintypes.HANDLE, ctypes.c_void_p], wintypes.BOOL),
        (user32, "SetProcessDPIAware", [], wintypes.BOOL),
        (kernel32, "GetCurrentThreadId", [], wintypes.DWORD),
        (kernel32, "OpenProcess", [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        (kernel32, "QueryFullProcessImageNameW", [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, pointer_to_dword], wintypes.BOOL),
        (kernel32, "CloseHandle", [wintypes.HANDLE], wintypes.BOOL),
    )
    for library, name, argtypes, restype in declarations:
        _declare(library, name, argtypes, restype)


def configure_shcore_api(shcore: Any) -> None:
    pointer_to_uint = ctypes.POINTER(wintypes.UINT)
    _declare(
        shcore,
        "GetDpiForMonitor",
        [wintypes.HANDLE, ctypes.c_int, pointer_to_uint, pointer_to_uint],
        wintypes.LONG,
    )
    _declare(
        shcore,
        "SetProcessDpiAwareness",
        [ctypes.c_int],
        wintypes.LONG,
    )


def _declare(
    library: Any,
    name: str,
    argtypes: list[Any],
    restype: Any,
) -> None:
    function = getattr(library, name, None)
    if function is None:
        return
    try:
        function.argtypes = argtypes
        function.restype = restype
    except (AttributeError, TypeError):
        # Python test doubles expose bound methods rather than ctypes functions.
        return
