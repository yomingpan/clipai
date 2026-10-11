import ctypes

from ClipAI.platform.window_activation import activate_top_level_window


class Kernel32:
    def GetCurrentThreadId(self) -> int:
        return 1


class User32:
    def __init__(self) -> None:
        self.foreground = 30
        self.attached: list[tuple[int, int, bool]] = []
        self.brought_to_top: list[int] = []
        self.active: list[int] = []

    def GetForegroundWindow(self) -> int:
        return self.foreground

    def GetWindowThreadProcessId(self, hwnd: int, _process_id) -> int:
        return {30: 2, 42: 3}[hwnd]

    def AttachThreadInput(self, current: int, related: int, attached: bool) -> bool:
        self.attached.append((current, related, attached))
        return True

    def BringWindowToTop(self, hwnd: int) -> bool:
        self.brought_to_top.append(hwnd)
        return True

    def SetForegroundWindow(self, hwnd: int) -> bool:
        self.foreground = hwnd
        return True

    def SetActiveWindow(self, hwnd: int) -> int:
        self.active.append(hwnd)
        return 0


def test_activation_attaches_to_foreground_and_target_input_queues() -> None:
    user32 = User32()

    activated = activate_top_level_window(
        42,
        user32=user32,
        kernel32=Kernel32(),
    )

    assert activated is True
    assert user32.brought_to_top == [42]
    assert user32.active == [42]
    assert user32.attached == [
        (1, 2, True),
        (1, 3, True),
        (1, 3, False),
        (1, 2, False),
    ]


def test_activation_fails_closed_when_native_calls_are_unavailable() -> None:
    assert (
        activate_top_level_window(
            42,
            user32=object(),
            kernel32=object(),
        )
        is False
    )


def test_activation_temporarily_suspends_and_restores_foreground_lock() -> None:
    user32 = User32()
    user32.lock_timeout = 200_000
    user32.lock_events = []

    def system_parameters_info(action, _param, value, flags):
        if action == 0x2000:
            ctypes.cast(value, ctypes.POINTER(ctypes.c_uint32))[0] = user32.lock_timeout
            user32.lock_events.append(("get", user32.lock_timeout))
            return True
        previous = user32.lock_timeout
        user32.lock_timeout = int(value.value or 0)
        user32.lock_events.append(("set", previous, user32.lock_timeout, flags))
        return True

    original_set_foreground = user32.SetForegroundWindow

    def locked_set_foreground(hwnd: int) -> bool:
        if user32.lock_timeout:
            return False
        return original_set_foreground(hwnd)

    user32.SystemParametersInfoW = system_parameters_info
    user32.SetForegroundWindow = locked_set_foreground

    assert activate_top_level_window(42, user32=user32, kernel32=Kernel32()) is True
    assert user32.lock_timeout == 200_000
    assert user32.lock_events == [
        ("get", 200_000),
        ("set", 200_000, 0, 2),
        ("set", 0, 200_000, 2),
    ]
    assert user32.attached[-2:] == [(1, 3, False), (1, 2, False)]
