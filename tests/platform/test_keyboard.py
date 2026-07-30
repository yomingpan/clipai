from __future__ import annotations

import pytest

from ClipAI.platform.keyboard import SystemKeyboardOutput
from ClipAI.core.models import PasteTarget


TARGET = PasteTarget("hwnd:10", 42, "Notepad", "Untitled", 1)


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
        target_is_valid=lambda target: target == TARGET,
        activate_target=lambda target: target == TARGET,
        target_is_foreground=lambda target: target == TARGET,
    )

    keyboard.paste(TARGET)

    assert waits == [0.02]
    assert pasted == ["paste"]


def test_paste_fails_without_injecting_when_modifiers_do_not_release() -> None:
    pasted: list[str] = []
    keyboard = SystemKeyboardOutput(
        modifier_is_pressed=lambda _modifier: True,
        modifier_release_timeout_sec=0,
        wait=lambda _delay: None,
        paste_shortcut=lambda: pasted.append("paste"),
        target_is_valid=lambda _target: True,
        activate_target=lambda _target: True,
        target_is_foreground=lambda _target: True,
    )

    with pytest.raises(RuntimeError, match="modifiers were not released"):
        keyboard.paste(TARGET)

    assert pasted == []


def test_paste_rejects_invalid_target_without_injecting() -> None:
    pasted: list[str] = []
    keyboard = SystemKeyboardOutput(
        modifier_is_pressed=lambda _modifier: False,
        paste_shortcut=lambda: pasted.append("paste"),
        target_is_valid=lambda _target: False,
        activate_target=lambda _target: True,
        target_is_foreground=lambda _target: True,
    )

    with pytest.raises(RuntimeError, match="找不到貼上目標"):
        keyboard.paste(TARGET)

    assert pasted == []
