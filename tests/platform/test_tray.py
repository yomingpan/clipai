from __future__ import annotations

from clipai.platform.tray import TrayIcon


def test_tray_tts_state_maps_requesting_and_buffering_to_processing() -> None:
    tray = object.__new__(TrayIcon)
    seen: list[tuple[str, object]] = []
    tray._on_ui_status = lambda **kwargs: seen.append((kwargs["status"], kwargs.get("reset_after")))

    tray._on_tts_state({"phase": "requesting", "is_speaking": True})
    tray._on_tts_state({"phase": "buffering", "is_speaking": True})

    assert seen == [("processing", 0), ("processing", 0)]


def test_tray_tts_state_maps_start_and_end_to_visible_icon_states() -> None:
    tray = object.__new__(TrayIcon)
    seen: list[tuple[str, object]] = []
    tray._on_ui_status = lambda **kwargs: seen.append((kwargs["status"], kwargs.get("reset_after")))

    tray._on_tts_state({"phase": "start", "is_speaking": True})
    tray._on_tts_state({"phase": "end", "is_speaking": False})

    assert seen == [("success", 0), ("idle", 0)]
