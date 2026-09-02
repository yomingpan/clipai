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
