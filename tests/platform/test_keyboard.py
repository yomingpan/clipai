from __future__ import annotations

import pytest

from ClipAI.platform.keyboard import SystemKeyboardOutput


def test_paste_waits_for_physical_modifiers_to_be_released() -> None:
    ctrl_pressed = [True]
    waits: list[float] = []
    pasted: list[str] = []

    def modifier_is_pressed(modifier: str) -> bool:
        return modifier == "ctrl" and ctrl_pressed[0]

    def wait(delay: float) -> None:
        waits.append(delay)
        ctrl_pressed[0] = False

    keyboard = SystemKeyboardOutput(
        modifier_is_pressed=modifier_is_pressed,
        poll_sec=0.02,
        wait=wait,
        paste_shortcut=lambda: pasted.append("paste"),
    )

    keyboard.paste()

    assert waits == [0.02]
    assert pasted == ["paste"]


def test_paste_fails_without_injecting_when_modifiers_do_not_release() -> None:
    pasted: list[str] = []
    keyboard = SystemKeyboardOutput(
        modifier_is_pressed=lambda _modifier: True,
        modifier_release_timeout_sec=0,
        wait=lambda _delay: None,
        paste_shortcut=lambda: pasted.append("paste"),
    )

    with pytest.raises(RuntimeError, match="modifiers were not released"):
        keyboard.paste()

    assert pasted == []
