from __future__ import annotations

from pathlib import Path

from ClipAI.platform.voice_webview_host import voice_webview_profile_dir


def test_voice_webview_profile_is_stable_for_the_current_user(tmp_path: Path) -> None:
    local_app_data = tmp_path / "AppData" / "Local"

    first = voice_webview_profile_dir(local_app_data)
    second = voice_webview_profile_dir(local_app_data)

    assert first == local_app_data / "ClipAI" / "VoiceWebView"
    assert first == second
    assert first.is_dir()
