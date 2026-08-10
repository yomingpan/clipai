from __future__ import annotations

import threading
from pathlib import Path

from ClipAI.platform.voice_webview_host import (
    _Api,
    _dispatch_host_command,
    allow_microphone_permission,
    is_explicit_voice_microphone_request,
    show_permission_surface_without_activation,
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
        self.javascript: list[str] = []

    def show(self) -> None:
        self.display_calls.append("show")

    def restore(self) -> None:
        self.display_calls.append("restore")

    def focus(self) -> None:
        self.display_calls.append("focus")

    def evaluate_js(self, script: str) -> None:
        self.javascript.append(script)


class NativeWindow:
    Handle = 42


class PermissionSurfaceWindow:
    native = NativeWindow()


class User32:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def GetWindowLongW(self, handle, index):
        self.calls.append(("get", handle, index))
        return 0

    def SetWindowLongW(self, handle, index, value):
        self.calls.append(("set", handle, index, value))

    def SetWindowPos(self, *args):
        self.calls.append(("position", *args))

    def ShowWindow(self, handle, mode):
        self.calls.append(("show", handle, mode))


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


def test_permission_surface_is_a_non_activating_tool_window() -> None:
    user32 = User32()

    assert show_permission_surface_without_activation(PermissionSurfaceWindow(), user32=user32) is True

    assert user32.calls[-1] == ("show", 42, 4)
    assert any(call[0] == "position" and call[3:7] == (-32000, -32000, 1, 1) for call in user32.calls)


def test_voice_commands_do_not_show_or_focus_the_hidden_host_window() -> None:
    window = VoiceWindow()
    loaded = threading.Event()
    loaded.set()
    assert _dispatch_host_command(
        window,
        _Api(threading.Event()),
        {"command": "start", "capture_id": "capture-1"},
        loaded=loaded,
    ) is True

    assert window.display_calls == []
    assert len(window.javascript) == 1
