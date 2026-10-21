from __future__ import annotations

import ctypes
from collections.abc import Callable
from ctypes import wintypes
from pathlib import Path
from typing import Any

from ClipAI.platform.window_activation import activate_top_level_window
from ClipAI.platform.win32_api import configure_win32_api


GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_NOACTIVATE = 0x08000000
SW_SHOWNOACTIVATE = 4
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
WM_SETICON = 0x0080
ICON_SMALL = 0
ICON_BIG = 1
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
DEFAULT_CHARSET = 1


class _LOGFONTW(ctypes.Structure):
    _fields_ = [
        ("lfHeight", wintypes.LONG),
        ("lfWidth", wintypes.LONG),
        ("lfEscapement", wintypes.LONG),
        ("lfOrientation", wintypes.LONG),
        ("lfWeight", wintypes.LONG),
        ("lfItalic", wintypes.BYTE),
        ("lfUnderline", wintypes.BYTE),
        ("lfStrikeOut", wintypes.BYTE),
        ("lfCharSet", wintypes.BYTE),
        ("lfOutPrecision", wintypes.BYTE),
        ("lfClipPrecision", wintypes.BYTE),
        ("lfQuality", wintypes.BYTE),
        ("lfPitchAndFamily", wintypes.BYTE),
        ("lfFaceName", wintypes.WCHAR * 32),
    ]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("size", wintypes.DWORD), ("width", wintypes.LONG), ("height", wintypes.LONG),
        ("planes", wintypes.WORD), ("bits", wintypes.WORD),
        ("compression", wintypes.DWORD), ("image_size", wintypes.DWORD),
        ("xppm", wintypes.LONG), ("yppm", wintypes.LONG),
        ("used", wintypes.DWORD), ("important", wintypes.DWORD),
    ]


def _capture_region_rgb(user32: Any, x: int, y: int, width: int, height: int) -> bytes | None:
    """Copy only the required desktop rectangle; retain no native resources."""
    from PIL import Image
    gdi = ctypes.windll.gdi32
    handle = wintypes.HANDLE
    integer = ctypes.c_int
    declarations = (
        (user32.GetDC, [wintypes.HWND], handle),
        (user32.ReleaseDC, [wintypes.HWND, handle], integer),
        (gdi.CreateCompatibleDC, [handle], handle),
        (gdi.CreateCompatibleBitmap, [handle, integer, integer], handle),
        (gdi.SelectObject, [handle, handle], handle),
        (gdi.BitBlt, [handle, integer, integer, integer, integer, handle, integer, integer, wintypes.DWORD], wintypes.BOOL),
        (gdi.GetDIBits, [handle, handle, wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT], integer),
        (gdi.DeleteObject, [handle], wintypes.BOOL),
        (gdi.DeleteDC, [handle], wintypes.BOOL),
    )
    for function, arguments, result in declarations:
        function.argtypes, function.restype = arguments, result
    screen = memory = bitmap = previous = None
    try:
        screen = user32.GetDC(0)
        if not screen:
            return None
        memory = gdi.CreateCompatibleDC(screen)
        if not memory:
            return None
        bitmap = gdi.CreateCompatibleBitmap(screen, width, height)
        if not bitmap:
            return None
        previous = gdi.SelectObject(memory, bitmap)
        if not previous or previous == ctypes.c_void_p(-1).value:
            previous = None
            return None
        if not gdi.BitBlt(memory, 0, 0, width, height, screen, x, y, 0x40CC0020):
            return None
        gdi.SelectObject(memory, previous)
        previous = None
        header = _BITMAPINFOHEADER(size=ctypes.sizeof(_BITMAPINFOHEADER), width=width, height=-height, planes=1, bits=32)
        data = ctypes.create_string_buffer(width * height * 4)
        if gdi.GetDIBits(memory, bitmap, 0, height, data, ctypes.byref(header), 0) != height:
            return None
        return Image.frombytes("RGB", (width, height), data.raw, "raw", "BGRX").tobytes()
    finally:
        if previous:
            gdi.SelectObject(memory, previous)
        if bitmap:
            gdi.DeleteObject(bitmap)
        if memory:
            gdi.DeleteDC(memory)
        if screen:
            user32.ReleaseDC(0, screen)


class WindowsNativeWindowSurface:
    """Conservative Windows adapter for native facts about toolkit windows."""

    def __init__(
        self,
        *,
        user32: Any | None = None,
        kernel32: Any | None = None,
        imm32: Any | None = None,
        shell32: Any | None = None,
        screen_grabber: Callable[..., Any] | None = None,
    ) -> None:
        self._user32 = user32 or ctypes.windll.user32
        self._kernel32 = kernel32 or ctypes.windll.kernel32
        self._imm32 = imm32 or ctypes.windll.imm32
        self._shell32 = shell32 or ctypes.windll.shell32
        self._screen_grabber = screen_grabber
        configure_win32_api(self._user32, self._kernel32)

    def prevent_click_activation(self, toolkit_child_id: int) -> bool:
        try:
            hwnd = self._top_level(toolkit_child_id)
            style = int(self._user32.GetWindowLongW(hwnd, GWL_EXSTYLE))
            self._user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE)
            self._user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0037)
            return bool(int(self._user32.GetWindowLongW(hwnd, GWL_EXSTYLE)) & WS_EX_NOACTIVATE)
        except (AttributeError, OSError, TypeError, ValueError):
            return False

    def capture_screen_rgb(self, x: int, y: int, width: int, height: int) -> bytes | None:
        if width <= 0 or height <= 0:
            return None
        try:
            grab = self._screen_grabber
            if grab is None:
                return _capture_region_rgb(self._user32, x, y, width, height)
            image = grab(bbox=(x, y, x + width, y + height), all_screens=True).convert("RGB")
            if image.size != (width, height):
                return None
            pixels = image.tobytes()
            return pixels if len(pixels) == width * height * 3 else None
        except (AttributeError, OSError, TypeError, ValueError):
            return None

    def set_process_taskbar_identity(self, app_id: str) -> bool:
        try:
            return int(self._shell32.SetCurrentProcessExplicitAppUserModelID(app_id)) == 0
        except (AttributeError, OSError, TypeError, ValueError):
            return False

    def hide_from_task_switcher(self, toolkit_child_id: int) -> bool:
        try:
            hwnd = self._top_level(toolkit_child_id)
            style = int(self._user32.GetWindowLongW(hwnd, GWL_EXSTYLE))
            self._user32.SetWindowLongW(
                hwnd,
                GWL_EXSTYLE,
                (style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW,
            )
            self._user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
            return True
        except (AttributeError, OSError, TypeError, ValueError):
            return False

    def activate(self, toolkit_child_id: int) -> bool:
        try:
            hwnd = self._top_level(toolkit_child_id)
            # Tk has already deiconified the window before it asks for native
            # activation. Re-showing it here produces a second visible frame
            # on Windows, which is especially noticeable for the Entry Panel.
            self._user32.SetWindowPos(
                hwnd,
                -1,
                0,
                0,
                0,
                0,
                SWP_NOSIZE | SWP_NOMOVE,
            )
            return activate_top_level_window(
                hwnd,
                user32=self._user32,
                kernel32=self._kernel32,
            )
        except (AttributeError, OSError, TypeError, ValueError):
            return False

    def show_without_activation(self, toolkit_child_id: int) -> bool:
        try:
            previous_foreground = int(self._user32.GetForegroundWindow())
            hwnd = self._top_level(toolkit_child_id)
            self._user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
            foreground_after_show = int(self._user32.GetForegroundWindow())
            if (
                previous_foreground
                and previous_foreground != hwnd
                and foreground_after_show == hwnd
            ):
                activate_top_level_window(
                    previous_foreground,
                    user32=self._user32,
                    kernel32=self._kernel32,
                )
            return (
                int(self._user32.GetForegroundWindow()) == previous_foreground
                if previous_foreground
                else True
            )
        except (AttributeError, OSError, TypeError, ValueError):
            return False

    def owns_foreground(self, toolkit_child_id: int) -> bool:
        try:
            return int(self._user32.GetForegroundWindow()) == self._top_level(toolkit_child_id)
        except (AttributeError, OSError, TypeError, ValueError):
            return False

    def set_ime_composition_font(
        self,
        toolkit_child_id: int,
        *,
        family: str,
        height: int,
        weight: int,
        italic: bool,
    ) -> bool:
        context = 0
        hwnd = 0
        try:
            hwnd = self._top_level(toolkit_child_id)
            context = int(self._imm32.ImmGetContext(hwnd))
            if not context:
                return False
            font = _LOGFONTW()
            font.lfHeight = int(height)
            font.lfWeight = int(weight)
            font.lfItalic = 1 if italic else 0
            font.lfCharSet = DEFAULT_CHARSET
            font.lfFaceName = str(family)[:31]
            return bool(self._imm32.ImmSetCompositionFontW(context, ctypes.byref(font)))
        except (AttributeError, OSError, TypeError, ValueError):
            return False
        finally:
            if context:
                try:
                    self._imm32.ImmReleaseContext(hwnd, context)
                except (AttributeError, OSError, TypeError, ValueError):
                    pass

    def install_icon(self, toolkit_child_id: int, icon_path: Path) -> tuple[int, ...]:
        small_icon = 0
        large_icon = 0
        try:
            hwnd = self._top_level(toolkit_child_id)
            small_icon = int(self._user32.LoadImageW(None, str(icon_path), IMAGE_ICON, 16, 16, LR_LOADFROMFILE))
            large_icon = int(self._user32.LoadImageW(None, str(icon_path), IMAGE_ICON, 32, 32, LR_LOADFROMFILE))
            if not small_icon or not large_icon:
                self.destroy_icons(tuple(handle for handle in (small_icon, large_icon) if handle))
                return ()
            self._user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, small_icon)
            self._user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, large_icon)
            return small_icon, large_icon
        except (AttributeError, OSError, TypeError, ValueError):
            self.destroy_icons(tuple(handle for handle in (small_icon, large_icon) if handle))
            return ()

    def destroy_icons(self, handles: tuple[int, ...]) -> None:
        for handle in handles:
            try:
                self._user32.DestroyIcon(handle)
            except (AttributeError, OSError, TypeError, ValueError):
                pass

    def _top_level(self, toolkit_child_id: int) -> int:
        child = int(toolkit_child_id)
        parent = int(self._user32.GetParent(child))
        return parent or child


class HeadlessNativeWindowSurface:
    """Conservative adapter for environments with no native window system."""

    def set_process_taskbar_identity(self, app_id: str) -> bool:
        return False

    def hide_from_task_switcher(self, toolkit_child_id: int) -> bool:
        return False

    def activate(self, toolkit_child_id: int) -> bool:
        return False

    def show_without_activation(self, toolkit_child_id: int) -> bool:
        return False

    def prevent_click_activation(self, toolkit_child_id: int) -> bool:
        return False

    def capture_screen_rgb(self, x: int, y: int, width: int, height: int) -> bytes | None:
        return None

    def owns_foreground(self, toolkit_child_id: int) -> bool:
        return False

    def set_ime_composition_font(
        self,
        toolkit_child_id: int,
        *,
        family: str,
        height: int,
        weight: int,
        italic: bool,
    ) -> bool:
        return False

    def install_icon(self, toolkit_child_id: int, icon_path: Path) -> tuple[int, ...]:
        return ()

    def destroy_icons(self, handles: tuple[int, ...]) -> None:
        return None
