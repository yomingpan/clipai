from __future__ import annotations

import os


def open_microphone_privacy_settings() -> None:
    """Open the Windows-owned microphone permission repair surface."""
    os.startfile("ms-settings:privacy-microphone")  # type: ignore[attr-defined]
