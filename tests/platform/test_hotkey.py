from __future__ import annotations

from clipai.platform.hotkey import expand_hotkeys


def test_expand_hotkeys_keeps_legacy_and_adds_ctrl_alt_variant() -> None:
    assert expand_hotkeys("alt+shift+1", modifier_mode="ctrl_alt") == ["alt+shift+1", "ctrl+alt+1"]


def test_expand_hotkeys_ignores_non_legacy_prefix() -> None:
    assert expand_hotkeys("ctrl+shift+1", modifier_mode="ctrl_alt") == ["ctrl+shift+1"]
