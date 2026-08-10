from __future__ import annotations

import shutil
from pathlib import Path


def voice_webview_profile_path(local_app_data: Path) -> Path:
    return local_app_data / "ClipAI" / "VoiceWebView"


def voice_webview_profile_dir(local_app_data: Path) -> Path:
    """Return the app-owned WebView profile that retains microphone consent."""
    profile = voice_webview_profile_path(local_app_data)
    profile.mkdir(parents=True, exist_ok=True)
    return profile


def reset_voice_webview_profile(local_app_data: Path) -> None:
    """Remove only ClipAI's isolated Voice WebView profile after explicit user repair."""
    profile = voice_webview_profile_path(local_app_data)
    if profile.exists():
        if not profile.is_dir():
            raise OSError("ClipAI Voice WebView profile path is not a directory")
        shutil.rmtree(profile)
