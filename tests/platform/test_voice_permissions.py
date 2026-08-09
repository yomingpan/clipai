from __future__ import annotations

import os

from ClipAI.platform.voice_permissions import open_microphone_privacy_settings


def test_opens_windows_microphone_privacy_settings(monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(os, "startfile", opened.append, raising=False)

    open_microphone_privacy_settings()

    assert opened == ["ms-settings:privacy-microphone"]
