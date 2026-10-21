from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ClipAI.platform.native_window import HeadlessNativeWindowSurface, WindowsNativeWindowSurface


class Kernel32:
    def GetCurrentThreadId(self) -> int:
        return 1


class User32:
    def __init__(self) -> None:
        self.foreground = 30
        self.style = 0x00040000
        self.attached: list[tuple[int, int, bool]] = []
        self.positioned: list[tuple] = []
        self.shown: list[tuple[int, int]] = []
        self.restored: list[int] = []
        self.destroyed: list[int] = []
        self.messages: list[tuple] = []
        self.loaded_icons = [101, 102]

    def GetParent(self, child: int) -> int:
        return 20 if child == 10 else 0

    def GetWindowLongW(self, hwnd: int, index: int) -> int:
        assert (hwnd, index) == (20, -20)
        return self.style

    def SetWindowLongW(self, hwnd: int, index: int, style: int) -> None:
        self.style = style

    def SetWindowPos(self, *args) -> bool:
        self.positioned.append(args)
        return True

    def GetForegroundWindow(self) -> int:
        return self.foreground

    def GetWindowThreadProcessId(self, hwnd: int, _process_id) -> int:
        return 2 if hwnd == 30 else 1

    def AttachThreadInput(self, current: int, foreground: int, attached: bool) -> bool:
        self.attached.append((current, foreground, attached))
        return True

    def ShowWindow(self, hwnd: int, command: int) -> bool:
        self.shown.append((hwnd, command))
        return True

    def BringWindowToTop(self, _hwnd: int) -> bool:
        return True

    def SetForegroundWindow(self, hwnd: int) -> bool:
        self.foreground = hwnd
        self.restored.append(hwnd)
        return True

    def SetActiveWindow(self, _hwnd: int) -> int:
        return 0

    def LoadImageW(self, *_args) -> int:
        return self.loaded_icons.pop(0)

    def SendMessageW(self, *args) -> int:
        self.messages.append(args)
        return 0

    def DestroyIcon(self, handle: int) -> bool:
        self.destroyed.append(handle)
        return True


class Imm32:
    def __init__(self, context: int = 91) -> None:
        self.context = context
        self.fonts = []
        self.released = []

    def ImmGetContext(self, hwnd: int) -> int:
        return self.context

    def ImmSetCompositionFontW(self, context: int, font) -> bool:
        self.fonts.append((context, font._obj))
        return True

    def ImmReleaseContext(self, hwnd: int, context: int) -> bool:
        self.released.append((hwnd, context))
        return True


def test_noactivate_style_prevents_click_activation_without_moving_foreground():
    user32 = User32()
    surface = WindowsNativeWindowSurface(user32=user32, kernel32=Kernel32())
    assert surface.prevent_click_activation(10) is True
    assert user32.style & 0x08000000
    assert user32.foreground == 30
    assert user32.restored == []
    assert user32.positioned[-1][-1] & 0x0010  # SWP_NOACTIVATE


def test_rgb_capture_returns_only_memory_bytes_and_rejects_invalid_bounds():
    captures = []
    class Image:
        size = (2, 1)
        def convert(self, mode):
            assert mode == "RGB"
            return self
        def tobytes(self):
            return b"\x01\x02\x03\x04\x05\x06"
    def grab(**kwargs):
        captures.append(kwargs)
        return Image()
    surface = WindowsNativeWindowSurface(user32=User32(), kernel32=Kernel32(), screen_grabber=grab)
    assert surface.capture_screen_rgb(-5, 7, 2, 1) == b"\x01\x02\x03\x04\x05\x06"
    assert captures == [{"bbox": (-5, 7, -3, 8), "all_screens": True}]
    assert surface.capture_screen_rgb(0, 0, 0, 1) is None
    assert len(captures) == 1


def test_default_rgb_capture_copies_only_requested_region_and_releases_gdi_handles(monkeypatch):
    import ctypes
    from ClipAI.platform import native_window
    calls = []
    class Function:
        def __init__(self, callback): self.callback = callback
        def __call__(self, *args): return self.callback(*args)
    class API:
        pass
    user, gdi = API(), API()
    user.GetDC = Function(lambda hwnd: 100)
    user.ReleaseDC = Function(lambda hwnd, dc: calls.append(("release", dc)))
    gdi.CreateCompatibleDC = Function(lambda dc: 101)
    gdi.CreateCompatibleBitmap = Function(lambda dc, w, h: 102)
    gdi.SelectObject = Function(lambda dc, obj: calls.append(("select", obj)) or 103)
    gdi.BitBlt = Function(lambda *args: calls.append(("copy", args)) or 1)
    def pixels(dc, bitmap, start, rows, data, info, usage):
        ctypes.memmove(data, b"\x03\x02\x01\x00\x06\x05\x04\x00", 8)
        return rows
    gdi.GetDIBits = Function(pixels)
    gdi.DeleteObject = Function(lambda obj: calls.append(("delete_bitmap", obj)))
    gdi.DeleteDC = Function(lambda dc: calls.append(("delete_dc", dc)))
    monkeypatch.setattr(ctypes.windll, "gdi32", gdi)
    surface = WindowsNativeWindowSurface(user32=user, kernel32=Kernel32())
    assert surface.capture_screen_rgb(-5, 7, 2, 1) == b"\x01\x02\x03\x04\x05\x06"
    assert ("copy", (101, 0, 0, 2, 1, 100, -5, 7, 0x40CC0020)) in calls
    assert calls[-3:] == [("delete_bitmap", 102), ("delete_dc", 101), ("release", 100)]
    calls.clear()
    gdi.BitBlt = Function(lambda *args: 0)
    assert surface.capture_screen_rgb(0, 0, 2, 1) is None
    assert calls[-3:] == [("delete_bitmap", 102), ("delete_dc", 101), ("release", 100)]


def test_windows_surface_resolves_top_level_and_hides_task_switcher_entry() -> None:
    user32 = User32()
    surface = WindowsNativeWindowSurface(user32=user32, kernel32=Kernel32())

    assert surface.hide_from_task_switcher(10) is True

    assert user32.style == 0x00000080
    assert user32.positioned[-1][-1] == 0x0027


def test_windows_surface_activates_and_verifies_foreground_ownership() -> None:
    user32 = User32()
    surface = WindowsNativeWindowSurface(user32=user32, kernel32=Kernel32())

    assert surface.activate(10) is True

    assert user32.attached == [(1, 2, True), (1, 2, False)]
    # Toolkit has already made the Toplevel visible before activation. Native
    # activation must not issue a second show operation, which flashes a
    # cursor-adjacent Panel on Windows.
    assert user32.shown == []
    assert user32.positioned[-1] == (20, -1, 0, 0, 0, 0, 0x0003)
    assert surface.owns_foreground(10) is True


def test_windows_surface_shows_without_activation_and_restores_external_foreground() -> None:
    user32 = User32()
    original_show = user32.ShowWindow
    def stealing_show(hwnd: int, command: int) -> bool:
        original_show(hwnd, command)
        user32.foreground = hwnd
        return True
    user32.ShowWindow = stealing_show
    surface = WindowsNativeWindowSurface(user32=user32, kernel32=Kernel32())

    assert surface.show_without_activation(10) is True

    assert user32.shown == [(20, 4)]
    assert user32.restored == [30]


def test_windows_surface_does_not_reactivate_when_no_activate_show_preserves_foreground() -> None:
    user32 = User32()
    surface = WindowsNativeWindowSurface(user32=user32, kernel32=Kernel32())

    assert surface.show_without_activation(10) is True

    assert user32.shown == [(20, 4)]
    assert user32.restored == []


def test_windows_surface_owns_icon_handles_until_explicit_destroy() -> None:
    user32 = User32()
    surface = WindowsNativeWindowSurface(user32=user32, kernel32=Kernel32())

    handles = surface.install_icon(10, Path("clipai.ico"))
    surface.destroy_icons(handles)

    assert handles == (101, 102)
    assert [message[2] for message in user32.messages] == [0, 1]
    assert user32.destroyed == [101, 102]


def test_native_surface_adapters_never_raise_when_os_facts_are_unavailable() -> None:
    broken = WindowsNativeWindowSurface(user32=object(), kernel32=object(), shell32=object())
    headless = HeadlessNativeWindowSurface()

    for surface in (broken, headless):
        assert surface.set_process_taskbar_identity("ClipAI.Desktop") is False
        assert surface.hide_from_task_switcher(10) is False
        assert surface.activate(10) is False
        assert surface.show_without_activation(10) is False
        assert surface.owns_foreground(10) is False
        assert surface.install_icon(10, Path("missing.ico")) == ()
        assert surface.set_ime_composition_font(10, family="Test", height=-16, weight=400, italic=False) is False
        surface.destroy_icons((1, 2))


def test_windows_surface_sets_process_taskbar_identity_only_when_requested() -> None:
    class Shell32:
        def __init__(self, result: int) -> None:
            self.result = result
            self.calls: list[str] = []

        def SetCurrentProcessExplicitAppUserModelID(self, app_id: str) -> int:
            self.calls.append(app_id)
            return self.result

    shell = Shell32(0)
    surface = WindowsNativeWindowSurface(user32=User32(), kernel32=Kernel32(), shell32=shell)
    assert shell.calls == []
    assert surface.set_process_taskbar_identity("ClipAI.Desktop") is True
    assert shell.calls == ["ClipAI.Desktop"]

    failure = WindowsNativeWindowSurface(user32=User32(), kernel32=Kernel32(), shell32=Shell32(1))
    assert failure.set_process_taskbar_identity("ClipAI.Desktop") is False


def test_windows_surface_sets_ime_font_and_releases_context() -> None:
    imm32 = Imm32()
    surface = WindowsNativeWindowSurface(user32=User32(), kernel32=Kernel32(), imm32=imm32)

    assert surface.set_ime_composition_font(
        10, family="A" * 40, height=-18, weight=700, italic=True
    ) is True

    font = imm32.fonts[0][1]
    assert (font.lfHeight, font.lfWeight, font.lfItalic) == (-18, 700, 1)
    assert font.lfFaceName == "A" * 31
    assert imm32.released == [(20, 91)]


def test_windows_surface_does_not_set_ime_font_without_context() -> None:
    imm32 = Imm32(context=0)
    surface = WindowsNativeWindowSurface(user32=User32(), kernel32=Kernel32(), imm32=imm32)

    assert surface.set_ime_composition_font(
        10, family="Test", height=-16, weight=400, italic=False
    ) is False
    assert imm32.fonts == []
