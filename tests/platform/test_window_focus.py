from ClipAI.platform.window_focus import EVENT_SYSTEM_FOREGROUND, WindowsForegroundWindowMonitor


class User32:
    def __init__(self) -> None:
        self.callback = None
        self.unhooked = None

    def SetWinEventHook(self, event_min, event_max, module, callback, process, thread, flags):
        assert (event_min, event_max) == (EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND)
        assert (module, process, thread, flags) == (0, 0, 0, 0)
        self.callback = callback
        return 99

    def GetForegroundWindow(self):
        return 10

    def UnhookWinEvent(self, hook):
        self.unhooked = hook


def test_monitor_reports_initial_and_later_external_foreground_windows() -> None:
    user32 = User32()
    targets = []
    monitor = WindowsForegroundWindowMonitor(
        targets.append,
        user32=user32,
        process_id=7,
        callback_factory=lambda callback: callback,
        read_target=lambda handle, own_pid: (42, "Notepad", f"Window {handle}") if own_pid == 7 else None,
    )

    monitor.start()
    user32.callback(None, EVENT_SYSTEM_FOREGROUND, 20, 0, 0, 0, 0)
    monitor.stop()

    assert [target.window_token for target in targets] == ["hwnd:a", "hwnd:14"]
    assert [target.observation_sequence for target in targets] == [1, 2]
    assert targets[-1].application_name == "Notepad"
    assert user32.unhooked == 99


def test_monitor_ignores_targets_rejected_by_platform_reader() -> None:
    user32 = User32()
    targets = []
    monitor = WindowsForegroundWindowMonitor(
        targets.append,
        user32=user32,
        process_id=7,
        callback_factory=lambda callback: callback,
        read_target=lambda _handle, _own_pid: None,
    )

    monitor.start()
    user32.callback(None, EVENT_SYSTEM_FOREGROUND, 20, 0, 0, 0, 0)
    monitor.stop()

    assert targets == []
