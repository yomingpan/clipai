from __future__ import annotations

import ctypes
from importlib.resources import as_file, files
import sys


CUSTOMTKINTER_ICON_DELAY_MS = 250
_WM_SETICON = 0x0080
_ICON_SMALL = 0
_ICON_BIG = 1
_IMAGE_ICON = 1
_LR_LOADFROMFILE = 0x0010


def install_clipai_window_icons(window) -> tuple[int, ...]:
    """Set ClipAI's title-bar and taskbar icon after CustomTkinter's default icon."""
    if sys.platform != "win32":
        return ()

    user32 = ctypes.windll.user32
    user32.GetParent.argtypes = (ctypes.c_void_p,)
    user32.GetParent.restype = ctypes.c_void_p
    user32.LoadImageW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_uint)
    user32.LoadImageW.restype = ctypes.c_void_p
    user32.SendMessageW.argtypes = (ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p)
    user32.SendMessageW.restype = ctypes.c_void_p
    user32.DestroyIcon.argtypes = (ctypes.c_void_p,)
    window_handle = user32.GetParent(window.winfo_id())
    if not window_handle:
        raise OSError("Unable to resolve the native ClipAI window")

    icon_resource = files("ClipAI.ui").joinpath("assets", "clipai.ico")
    with as_file(icon_resource) as icon_path:
        small_icon = user32.LoadImageW(None, str(icon_path), _IMAGE_ICON, 16, 16, _LR_LOADFROMFILE)
        large_icon = user32.LoadImageW(None, str(icon_path), _IMAGE_ICON, 32, 32, _LR_LOADFROMFILE)
    if not small_icon or not large_icon:
        if small_icon:
            user32.DestroyIcon(small_icon)
        if large_icon:
            user32.DestroyIcon(large_icon)
        raise OSError("Unable to load the ClipAI window icon")

    user32.SendMessageW(window_handle, _WM_SETICON, _ICON_SMALL, small_icon)
    user32.SendMessageW(window_handle, _WM_SETICON, _ICON_BIG, large_icon)
    return int(small_icon), int(large_icon)


def destroy_window_icons(handles: tuple[int, ...]) -> None:
    if sys.platform != "win32":
        return
    for icon_handle in handles:
        ctypes.windll.user32.DestroyIcon(icon_handle)
