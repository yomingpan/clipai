import subprocess
import sys

import pytest

from ClipAI.platform.window_focus import EVENT_SYSTEM_FOREGROUND, WindowsForegroundWindowMonitor


class User32:
    def __init__(self) -> None:
        self.callback = None
        self.unhooked = None
        self.hook_calls = 0
        self.unhook_result = True

    def SetWinEventHook(self, event_min, event_max, module, callback, process, thread, flags):
        assert (event_min, event_max) == (EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND)
        assert (module, process, thread, flags) == (0, 0, 0, 0)
        self.hook_calls += 1
        self.callback = callback
        return 99

    def GetForegroundWindow(self):
        return 10

    def UnhookWinEvent(self, hook):
        self.unhooked = hook
        return self.unhook_result


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


def test_monitor_never_reports_an_app_owned_helper_process_as_a_paste_target() -> None:
    user32 = User32()
    targets = []
    monitor = WindowsForegroundWindowMonitor(
        targets.append,
        user32=user32,
        process_id=7,
        is_owned_process=lambda process_id: process_id == 99,
        callback_factory=lambda callback: callback,
        read_target=lambda _handle, _own_pid: (99, "python", "ClipAI Voice Engine"),
    )

    monitor.start()
    user32.callback(None, EVENT_SYSTEM_FOREGROUND, 20, 0, 0, 0, 0)
    monitor.stop()

    assert targets == []


def test_monitor_retains_hook_ownership_when_native_unhook_fails() -> None:
    user32 = User32()
    user32.unhook_result = False
    monitor = WindowsForegroundWindowMonitor(
        lambda _target: None,
        user32=user32,
        process_id=7,
        callback_factory=lambda callback: callback,
        read_target=lambda _handle, _own_pid: None,
    )

    monitor.start()
    monitor.stop()
    monitor.start()

    assert user32.hook_calls == 1

    user32.unhook_result = True
    monitor.stop()


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="uses the real Windows event hook")
def test_real_foreground_hook_survives_repeated_start_and_stop() -> None:
    script = (
        "from ClipAI.platform.window_focus import WindowsForegroundWindowMonitor; "
        "[(lambda monitor: (monitor.start(), monitor.stop()))("
        "WindowsForegroundWindowMonitor(lambda _target: None)) "
        "for _ in range(100)]; "
        "print('hook-stress-ok', flush=True)"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, (
        result.returncode,
        result.stdout,
        result.stderr,
    )
    assert result.stdout.strip() == "hook-stress-ok"
