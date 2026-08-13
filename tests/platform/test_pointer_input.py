from __future__ import annotations

from ClipAI.platform.pointer_input import HeadlessPointerPressReader, WindowsPointerPressReader


def test_windows_pointer_reader_reports_each_press_once() -> None:
    class User32:
        def __init__(self) -> None:
            self.states = {0x01: 0x8001, 0x02: 0, 0x04: 0}

        def GetAsyncKeyState(self, button):
            return self.states[button]

        def GetCursorPos(self, pointer):
            pointer._obj.x = 321
            pointer._obj.y = 654
            return True

    user32 = User32()
    reader = WindowsPointerPressReader(user32)

    assert reader.poll() == (321, 654)
    user32.states[0x01] = 0x8000
    assert reader.poll() is None
    user32.states[0x01] = 0
    assert reader.poll() is None
    user32.states[0x01] = 0x8000
    assert reader.poll() == (321, 654)


def test_headless_pointer_reader_is_conservative() -> None:
    assert HeadlessPointerPressReader().poll() is None
