from __future__ import annotations

import ctypes
from pathlib import Path
from typing import Any


GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
SW_SHOWNOACTIVATE = 4
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
WM_SETICON = 0x0080
ICON_SMALL = 0
ICON_BIG = 1
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010


class WindowsNativeWindowSurface:
    """Conservative Windows adapter for native facts about toolkit windows."""

    def __init__(self, *, user32: Any | None = None, kernel32: Any | None = None) -> None:
        self._user32 = user32 or ctypes.windll.user32
        self._kernel32 = kernel32 or ctypes.windll.kernel32

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
        attached = False
        current_thread = 0
        foreground_thread = 0
        try:
            hwnd = self._top_level(toolkit_child_id)
            foreground = int(self._user32.GetForegroundWindow())
            current_thread = int(self._kernel32.GetCurrentThreadId())
            foreground_thread = (
                int(self._user32.GetWindowThreadProcessId(foreground, None))
                if foreground
                else 0
            )
            attached = bool(
                foreground_thread
                and foreground_thread != current_thread
                and self._user32.AttachThreadInput(current_thread, foreground_thread, True)
            )
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
            self._user32.BringWindowToTop(hwnd)
            self._user32.SetForegroundWindow(hwnd)
            self._user32.SetActiveWindow(hwnd)
            return int(self._user32.GetForegroundWindow()) == hwnd
        except (AttributeError, OSError, TypeError, ValueError):
            return False
        finally:
            if attached:
                try:
                    self._user32.AttachThreadInput(current_thread, foreground_thread, False)
                except (AttributeError, OSError, TypeError, ValueError):
                    pass

    def show_without_activation(self, toolkit_child_id: int) -> bool:
        try:
            previous_foreground = int(self._user32.GetForegroundWindow())
            hwnd = self._top_level(toolkit_child_id)
            self._user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
            if previous_foreground and previous_foreground != hwnd:
                self._user32.SetForegroundWindow(previous_foreground)
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

    def hide_from_task_switcher(self, toolkit_child_id: int) -> bool:
        return False

    def activate(self, toolkit_child_id: int) -> bool:
        return False

    def show_without_activation(self, toolkit_child_id: int) -> bool:
        return False

    def owns_foreground(self, toolkit_child_id: int) -> bool:
        return False

    def install_icon(self, toolkit_child_id: int, icon_path: Path) -> tuple[int, ...]:
        return ()

    def destroy_icons(self, handles: tuple[int, ...]) -> None:
        return None
