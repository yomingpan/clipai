from __future__ import annotations

from pathlib import Path

from ClipAI.platform.voice_webview_host import allow_microphone_permission, voice_webview_profile_dir


class PermissionRequest:
    def __init__(self, kind: object) -> None:
        self.PermissionKind = kind
        self.State = "default"
        self.SavesInProfile = False
        self.Handled = False


def test_voice_webview_profile_is_stable_for_the_current_user(tmp_path: Path) -> None:
    local_app_data = tmp_path / "AppData" / "Local"

    first = voice_webview_profile_dir(local_app_data)
    second = voice_webview_profile_dir(local_app_data)

    assert first == local_app_data / "ClipAI" / "VoiceWebView"
    assert first == second
    assert first.is_dir()


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


def test_non_microphone_permissions_keep_the_webview_default() -> None:
    request = PermissionRequest("camera")

    allow_microphone_permission(
        request,
        microphone_kind="microphone",
        allow_state="allow",
    )

    assert request.State == "default"
    assert request.SavesInProfile is False
    assert request.Handled is False
