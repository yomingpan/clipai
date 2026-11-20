import pytest

from ClipAI.core.hotkeys import canonicalize_hotkey, display_hotkey, parse_hotkey_tokens


@pytest.mark.parametrize("mode", ["ctrl_alt", "alt_shift", "ctrl_shift"])
def test_right_alt_is_a_solo_binding_independent_of_chord_modifier_mode(mode):
    assert canonicalize_hotkey("right_alt", mode) == "right_alt"
    assert parse_hotkey_tokens("right_alt") == frozenset({"altgr"})
    assert display_hotkey("right_alt") == "Right Alt"
