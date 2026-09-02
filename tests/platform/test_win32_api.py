from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys

import pytest

from ClipAI.platform.win32_api import configure_win32_api


@pytest.mark.skipif(sys.platform != "win32", reason="uses the real Windows ABI")
def test_native_window_handles_use_pointer_sized_ctypes_signatures() -> None:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    configure_win32_api(user32, kernel32)

    assert ctypes.sizeof(user32.GetForegroundWindow.restype) == ctypes.sizeof(
        ctypes.c_void_p
    )
    assert ctypes.sizeof(user32.SetWinEventHook.restype) == ctypes.sizeof(
        ctypes.c_void_p
    )
    assert ctypes.sizeof(kernel32.OpenProcess.restype) == ctypes.sizeof(
        ctypes.c_void_p
    )
    assert user32.GetWindowThreadProcessId.argtypes == [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
