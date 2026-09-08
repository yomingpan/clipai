"""Native menu masking for a consumed modifier shortcut, without text input."""
from __future__ import annotations

import ctypes
from ctypes import wintypes


class _KeyboardInput(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG), ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t),
    ]


class _HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _InputValue(ctypes.Union):
    _fields_ = [("ki", _KeyboardInput), ("mi", _MouseInput), ("hi", _HardwareInput)]


class _Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("value", _InputValue)]


def mask_alt_menu() -> None:
    """Insert an unassigned VK_E8 pair before forwarding a claimed Alt release.

    Windows/Qt otherwise interpret bare Alt-up as menu navigation. Do not inject
    Ctrl, Escape, text or a replacement Alt-up. The physical event must still be
    forwarded, so both the OS and the listener release the actual modifier.
    """
    # A fresh library wrapper keeps this INPUT signature independent of pynput's
    # own ctypes structure/signature on the shared ctypes.windll.user32 object.
    send_input = ctypes.WinDLL("user32", use_last_error=True).SendInput
    send_input.argtypes = (wintypes.UINT, ctypes.POINTER(_Input), ctypes.c_int)
    send_input.restype = wintypes.UINT
    inputs = (_Input * 2)(
        _Input(1, _InputValue(ki=_KeyboardInput(wVk=0xE8))),
        _Input(1, _InputValue(ki=_KeyboardInput(wVk=0xE8, dwFlags=2))),
    )
    sent = send_input(2, inputs, ctypes.sizeof(_Input))
    if sent != 2:
        if sent == 1:
            # Best effort to release only our unassigned key after partial input.
            send_input(1, ctypes.byref(inputs[1]), ctypes.sizeof(_Input))
        raise OSError("Windows rejected the Alt menu mask")
