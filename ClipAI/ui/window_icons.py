from __future__ import annotations

from importlib.resources import as_file, files

from ClipAI.core.ports import NativeWindowSurface


CUSTOMTKINTER_ICON_DELAY_MS = 250
def install_clipai_window_icons(window, native_window_surface: NativeWindowSurface) -> tuple[int, ...]:
    """Set ClipAI's title-bar and taskbar icon after CustomTkinter's default icon."""
    window.update_idletasks()
    toolkit_child_id = int(window.winfo_id())
    icon_resource = files("ClipAI.ui").joinpath("assets", "clipai.ico")
    with as_file(icon_resource) as icon_path:
        return native_window_surface.install_icon(toolkit_child_id, icon_path)


def destroy_window_icons(native_window_surface: NativeWindowSurface, handles: tuple[int, ...]) -> None:
    native_window_surface.destroy_icons(handles)
