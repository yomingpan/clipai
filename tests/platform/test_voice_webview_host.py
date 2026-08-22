from __future__ import annotations

import io
import sys
import threading
from types import SimpleNamespace
from pathlib import Path

from ClipAI.platform.voice_webview_host import (
    _Api,
    _dispatch_host_command,
    allow_microphone_permission,
    is_explicit_voice_microphone_request,
    main,
    realise_voice_host_invisibly,
    voice_webview_profile_dir,
)
from ClipAI.platform.voice_webview_profile import reset_voice_webview_profile


class PermissionRequest:
    def __init__(self, kind: object) -> None:
        self.PermissionKind = kind
        self.State = "default"
        self.SavesInProfile = False
        self.Handled = False


class VoiceWindow:
    def __init__(self) -> None:
        self.display_calls: list[str] = []
        self.lifecycle_calls: list[str] = []
        self.javascript: list[str] = []

    def show(self) -> None:
        self.display_calls.append("show")
        self.lifecycle_calls.append("show")

    def restore(self) -> None:
        self.display_calls.append("restore")

    def focus(self) -> None:
        self.display_calls.append("focus")

    def evaluate_js(self, script: str) -> None:
        self.javascript.append(script)


class IntPtr:
    def ToInt64(self) -> int:
        return 42

    def __int__(self) -> int:
        raise TypeError("pythonnet 3 System.IntPtr does not support int()")


class NativeWindow:
    def __init__(self, *, invoke_required: bool = False) -> None:
        self.Handle = IntPtr()
        self.Opacity = 1.0
        self.InvokeRequired = invoke_required
        self.calls: list[tuple[str, float]] = []

    def Show(self) -> None:
        self.calls.append(("show", self.Opacity))

    def Invoke(self, action) -> None:
        self.calls.append(("invoke", self.Opacity))
        action()


class PermissionSurfaceWindow:
    def __init__(self, *, invoke_required: bool = False) -> None:
        self.native = NativeWindow(invoke_required=invoke_required)


class User32:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def GetWindowLongW(self, handle, index):
        self.calls.append(("get", handle, index))
        return 0

    def SetWindowLongW(self, handle, index, value):
        self.calls.append(("set", handle, index, value))

def test_voice_webview_profile_is_stable_for_the_current_user(tmp_path: Path) -> None:
    local_app_data = tmp_path / "AppData" / "Local"

    first = voice_webview_profile_dir(local_app_data)
    second = voice_webview_profile_dir(local_app_data)

    assert first == local_app_data / "ClipAI" / "VoiceWebView"
    assert first == second
    assert first.is_dir()


def test_explicit_profile_repair_removes_only_the_app_owned_voice_profile(tmp_path: Path) -> None:
    local_app_data = tmp_path / "AppData" / "Local"
    profile = voice_webview_profile_dir(local_app_data)
    (profile / "permission-state").write_text("denied", encoding="utf-8")

    reset_voice_webview_profile(local_app_data)

    assert not profile.exists()
    assert local_app_data.exists()


def test_microphone_permission_is_allowed_saved_and_handled() -> None:
    request = PermissionRequest("microphone")

    allow_microphone_permission(
        request,
        microphone_kind="microphone",
        allow_state="allow",
    )

    assert request.State == "allow"
    assert request.SavesInProfile is True
    assert request.Handled is True


def test_only_explicit_setup_and_push_to_talk_capture_may_request_the_microphone() -> None:
    assert is_explicit_voice_microphone_request("prepare") is True
    assert is_explicit_voice_microphone_request("start") is True
    assert is_explicit_voice_microphone_request("stop") is False
    assert is_explicit_voice_microphone_request("cancel") is False
    assert is_explicit_voice_microphone_request("") is False


def test_non_microphone_permissions_keep_the_webview_default() -> None:
    request = PermissionRequest("camera")
    activations: list[str] = []

    allow_microphone_permission(
        request,
        microphone_kind="microphone",
        allow_state="allow",
        activate_host=lambda: activations.append("shown"),
    )

    assert request.State == "default"
    assert request.SavesInProfile is False
    assert request.Handled is False
    assert activations == []


def test_microphone_permission_uses_the_supplied_non_activating_surface() -> None:
    request = PermissionRequest("microphone")
    activations: list[str] = []

    allow_microphone_permission(
        request,
        microphone_kind="microphone",
        allow_state="allow",
        activate_host=lambda: activations.append("shown"),
    )

    assert activations == ["shown"]


def test_voice_host_is_realised_invisibly_with_an_intptr_handle() -> None:
    user32 = User32()
    window = PermissionSurfaceWindow()

    assert realise_voice_host_invisibly(window, user32=user32) is True

    assert window.native.calls == [("show", 0.0)]
    assert window.native.Opacity == 0.0
    assert [call[0] for call in user32.calls] == ["get", "set"]
    assert all(call[1] == 42 for call in user32.calls)


def test_voice_host_marshals_realisation_only_when_not_on_the_winforms_ui_thread() -> None:
    user32 = User32()
    window = PermissionSurfaceWindow(invoke_required=True)

    assert realise_voice_host_invisibly(window, user32=user32) is True

    assert window.native.calls == [("invoke", 1.0), ("show", 0.0)]


def test_prepare_and_start_realise_the_host_without_pywebview_show_or_focus() -> None:
    window = VoiceWindow()
    loaded = threading.Event()
    loaded.set()
    realised: list[str] = []

    def prepare_capture_surface(surface: VoiceWindow) -> bool:
        realised.append("surface")
        return True

    for command in (
        {"command": "prepare", "setup_id": "setup-1"},
        {"command": "start", "capture_id": "capture-1"},
    ):
        assert _dispatch_host_command(
            window,
            _Api(threading.Event()),
            command,
            loaded=loaded,
            capture_surface=prepare_capture_surface,
        ) is True

    assert realised == ["surface", "surface"]
    assert window.display_calls == []
    assert window.lifecycle_calls == []
    assert len(window.javascript) == 2


class CapturingApi(_Api):
    def __init__(self) -> None:
        super().__init__(threading.Event())
        self.events: list[dict[str, object]] = []

    def emit(self, payload: dict[str, object]) -> None:
        self.events.append(payload)


def test_prepare_and_start_fail_terminally_when_invisible_realisation_fails() -> None:
    loaded = threading.Event()
    loaded.set()

    cases = (
        ({"command": "prepare", "setup_id": "setup-1"}, "setup_failed"),
        ({"command": "start", "capture_id": "capture-1"}, "failed"),
    )
    for command, failure_kind in cases:
        window = VoiceWindow()
        api = CapturingApi()

        assert _dispatch_host_command(
            window,
            api,
            command,
            loaded=loaded,
            capture_surface=lambda _window: False,
        ) is True

        assert window.javascript == []
        assert api.events[0]["kind"] == failure_kind
        assert api.events[0]["failure"] == "initialization_failed"
        if command["command"] == "start":
            assert api.events[-1] == {"kind": "ended", "capture_id": "capture-1"}


def test_voice_host_exits_when_its_parent_transport_closes(monkeypatch, tmp_path: Path) -> None:
    destroyed = threading.Event()

    class LoadedEvent:
        def __iadd__(self, _callback):
            return self

    class Window:
        def __init__(self) -> None:
            self.events = SimpleNamespace(loaded=LoadedEvent())

        def destroy(self) -> None:
            destroyed.set()

    window = Window()
    fake_webview = SimpleNamespace(
        create_window=lambda *_args, **_kwargs: window,
        start=lambda **_kwargs: destroyed.wait(0.25),
    )
    monkeypatch.setitem(sys.modules, "webview", fake_webview)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))

    main(test_page=tmp_path / "voice.html", profile_root=tmp_path)

    assert destroyed.is_set()
