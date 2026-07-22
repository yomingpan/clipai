from __future__ import annotations

import sys


MODIFIER_KEYS = ("ctrl", "alt", "shift")

_MODIFIER_VIRTUAL_KEYS = {
    "alt": 0x12,  # VK_MENU
    "ctrl": 0x11,  # VK_CONTROL
    "shift": 0x10,  # VK_SHIFT
}


def windows_modifier_is_pressed(modifier: str) -> bool | None:
    """Return the physical modifier state when Windows can report it."""
    virtual_key = _MODIFIER_VIRTUAL_KEYS.get(modifier)
    if virtual_key is None or sys.platform != "win32":
        return None
    try:
        import ctypes

        return bool(ctypes.windll.user32.GetAsyncKeyState(virtual_key) & 0x8000)
    except (AttributeError, OSError):
        return None
