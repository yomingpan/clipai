from __future__ import annotations

from dataclasses import dataclass

import pytest

from ClipAI.platform.hotkey import create_hotkey_dispatcher, expand_hotkeys


@dataclass
class FakeKey:
    name: str | None = None
    char: str | None = None
    vk: int | None = None


class FakeTimer:
    timers: list["FakeTimer"] = []

    def __init__(self, interval: float, callback) -> None:
        self.interval = interval
        self.callback = callback
        self.cancelled = False
        self.started = False
        self.daemon = False
        FakeTimer.timers.append(self)

    def start(self) -> None:
        self.started = True

    def cancel(self) -> None:
        self.cancelled = True

    def fire(self) -> None:
        if not self.cancelled:
            self.callback()


def setup_function() -> None:
    FakeTimer.timers.clear()


def test_expand_hotkeys_adds_default_modifier_prefix() -> None:
    assert expand_hotkeys("8", modifier_mode="ctrl_alt") == ["ctrl+alt+8"]


def test_short_press_triggers_action_once() -> None:
    events: list[tuple[str, str]] = []
    dispatcher = create_hotkey_dispatcher(
        {"explain_word": {"hotkey": "ctrl+alt+8"}},
        lambda action_id, press_type: events.append((action_id, press_type)),
        modifier_mode="ctrl_alt",
        timer_factory=FakeTimer,
    )

    dispatcher.on_press(FakeKey(name="ctrl_l"))
    dispatcher.on_press(FakeKey(name="alt_l"))
    dispatcher.on_press(FakeKey(char="8"))
    dispatcher.on_release(FakeKey(char="8"))
    assert events == [("explain_word", "short")]
    dispatcher.on_release(FakeKey(name="alt_l"))
    assert events == [("explain_word", "short")]
    dispatcher.on_release(FakeKey(name="ctrl_l"))

    assert events == [("explain_word", "short")]
    assert len(FakeTimer.timers) == 1
    assert FakeTimer.timers[0].cancelled is True


@pytest.mark.parametrize(
    "action_key",
    [
        pytest.param(FakeKey(char="`"), id="unshifted-character"),
        pytest.param(FakeKey(char="~"), id="shifted-character"),
        pytest.param(FakeKey(char="輸", vk=192), id="windows-oem-key-under-ime"),
    ],
)
def test_grave_physical_key_triggers_tilde_shortcut_across_input_states(action_key: FakeKey) -> None:
    events: list[tuple[str, str]] = []
    dispatcher = create_hotkey_dispatcher(
        {"dictation_editor": {"hotkey": "ctrl+alt+~"}},
        lambda action_id, press_type: events.append((action_id, press_type)),
        modifier_mode="ctrl_alt",
        timer_factory=FakeTimer,
    )

    dispatcher.on_press(FakeKey(name="ctrl_l"))
    dispatcher.on_press(FakeKey(name="alt_l"))
    dispatcher.on_press(action_key)
    dispatcher.on_release(action_key)
    dispatcher.on_release(FakeKey(name="alt_l"))
    dispatcher.on_release(FakeKey(name="ctrl_l"))

    assert events == [("dictation_editor", "short")]
    assert len(FakeTimer.timers) == 1
    assert FakeTimer.timers[0].cancelled is True


def test_long_press_triggers_long_without_release_short() -> None:
    events: list[tuple[str, str]] = []
    dispatcher = create_hotkey_dispatcher(
        {"explain_word": {"hotkey": "ctrl+alt+8"}},
        lambda action_id, press_type: events.append((action_id, press_type)),
        modifier_mode="ctrl_alt",
        timer_factory=FakeTimer,
    )

    dispatcher.on_press(FakeKey(name="ctrl_l"))
    dispatcher.on_press(FakeKey(name="alt_l"))
    dispatcher.on_press(FakeKey(char="8"))
    FakeTimer.timers[0].fire()
    assert events == [("explain_word", "long")]
    dispatcher.on_release(FakeKey(char="8"))
    assert events == [("explain_word", "long"), ("explain_word", "long_release")]

    dispatcher.on_release(FakeKey(name="alt_l"))
    dispatcher.on_release(FakeKey(name="ctrl_l"))

    assert events == [("explain_word", "long"), ("explain_word", "long_release")]


def test_held_composer_fires_before_action_key_is_released() -> None:
    events: list[tuple[str, str]] = []
    dispatcher = create_hotkey_dispatcher(
        {
            "friend": {"hotkey": "ctrl+alt+6"},
            "speech": {"hotkey": "ctrl+alt+q"},
        },
        lambda action_id, press_type: events.append((action_id, press_type)),
        modifier_mode="ctrl_alt",
        timer_factory=FakeTimer,
    )

    dispatcher.on_press(FakeKey(name="ctrl_l"))
    dispatcher.on_press(FakeKey(name="alt_l"))
    dispatcher.on_press(FakeKey(char="q"))
    FakeTimer.timers[0].fire()
    dispatcher.on_press(FakeKey(char="6"))

    assert events == [("speech", "long")]

    dispatcher.on_release(FakeKey(char="6"))
    assert events == [("speech", "long"), ("friend", "short")]

    dispatcher.on_release(FakeKey(char="q"))
    dispatcher.on_release(FakeKey(name="alt_l"))
    dispatcher.on_release(FakeKey(name="ctrl_l"))

    assert events == [("speech", "long"), ("friend", "short"), ("speech", "long_release")]
