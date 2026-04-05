from __future__ import annotations

from types import SimpleNamespace

from clipai.platform.hotkey import _normalize_key, expand_hotkeys


def test_expand_hotkeys_uses_ctrl_alt_as_canonical_default() -> None:
    assert expand_hotkeys("ctrl+alt+1", modifier_mode="ctrl_alt") == ["ctrl+alt+1"]


def test_expand_hotkeys_rewrites_legacy_alt_shift_to_ctrl_alt() -> None:
    assert expand_hotkeys("alt+shift+1", modifier_mode="ctrl_alt") == ["ctrl+alt+1"]


def test_expand_hotkeys_keeps_ctrl_shift_when_requested() -> None:
    assert expand_hotkeys("ctrl+shift+1", modifier_mode="ctrl_shift") == ["ctrl+shift+1"]


def test_normalize_key_uses_vk_fallback_for_top_row_digits() -> None:
    assert _normalize_key(SimpleNamespace(vk=53)) == "5"


def test_normalize_key_uses_vk_fallback_for_numpad_digits() -> None:
    assert _normalize_key(SimpleNamespace(vk=101)) == "5"


def test_normalize_key_uses_vk_fallback_for_letters() -> None:
    assert _normalize_key(SimpleNamespace(vk=81)) == "q"
