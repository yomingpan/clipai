from __future__ import annotations

import sys


MODIFIER_KEYS = ("ctrl", "alt", "shift")

_TOKEN_VIRTUAL_KEYS = {
    "alt": (0x12,),  # VK_MENU
    "ctrl": (0x11,),  # VK_CONTROL
    "shift": (0x10,),  # VK_SHIFT
    "grave": (0xC0,),  # VK_OEM_3
    **{str(digit): (0x30 + digit, 0x60 + digit) for digit in range(10)},
    **{chr(code).lower(): (code,) for code in range(0x41, 0x5B)},
}


def windows_key_is_pressed(token: str) -> bool | None:
    """Return the physical state of a normalized hotkey token when available."""
    virtual_keys = _TOKEN_VIRTUAL_KEYS.get(token)
    if virtual_keys is None or sys.platform != "win32":
        return None
    try:
        import ctypes

        return any(
            bool(ctypes.windll.user32.GetAsyncKeyState(virtual_key) & 0x8000)
            for virtual_key in virtual_keys
        )
    except (AttributeError, OSError):
        return None


def windows_modifier_is_pressed(modifier: str) -> bool | None:
    """Return the physical modifier state when Windows can report it."""
    if modifier not in MODIFIER_KEYS:
        return None
    return windows_key_is_pressed(modifier)
