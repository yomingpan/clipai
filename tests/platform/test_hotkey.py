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
        lambda action_id, press_type, _gesture_id: events.append((action_id, press_type)),
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
        lambda action_id, press_type, _gesture_id: events.append((action_id, press_type)),
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
        lambda action_id, press_type, _gesture_id: events.append((action_id, press_type)),
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


def test_escape_interrupts_current_immediately_then_escalates_after_threshold() -> None:
    events: list[tuple[str, str]] = []
    dispatcher = create_hotkey_dispatcher(
        {},
        lambda action_id, press_type, _gesture_id: events.append((action_id, press_type)),
        timer_factory=FakeTimer,
    )

    dispatcher.on_press(FakeKey(name="esc"))
    assert events == [("", "interrupt_current")]
    assert len(FakeTimer.timers) == 1

    FakeTimer.timers[0].fire()
    assert events == [("", "interrupt_current"), ("", "interrupt_all")]

    dispatcher.on_release(FakeKey(name="esc"))
    dispatcher.on_press(FakeKey(name="esc"))
    dispatcher.on_release(FakeKey(name="esc"))
    assert FakeTimer.timers[-1].cancelled is True
    assert events[-1] == ("", "interrupt_current")


def test_escape_key_repeat_does_not_duplicate_current_interrupt() -> None:
    events: list[str] = []
    dispatcher = create_hotkey_dispatcher(
        {},
        lambda _action_id, press_type, _gesture_id: events.append(press_type),
        timer_factory=FakeTimer,
    )

    dispatcher.on_press(FakeKey(name="esc"))
    dispatcher.on_press(FakeKey(name="esc"))

    assert events == ["interrupt_current"]
    assert len(FakeTimer.timers) == 1


def test_held_composer_fires_before_action_key_is_released() -> None:
    events: list[tuple[str, str]] = []
    dispatcher = create_hotkey_dispatcher(
        {
            "friend": {"hotkey": "ctrl+alt+6"},
            "speech": {"hotkey": "ctrl+alt+q"},
        },
        lambda action_id, press_type, _gesture_id: events.append((action_id, press_type)),
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


def test_physical_gesture_progress_uses_one_identity_until_all_keys_release() -> None:
    triggers: list[tuple[str, str, int]] = []
    progress: list[tuple[int, frozenset[str], bool]] = []
    dispatcher = create_hotkey_dispatcher(
        {"english": {"hotkey": "ctrl+alt+8"}},
        lambda action_id, press_type, gesture_id: triggers.append((action_id, press_type, gesture_id)),
        on_progress=lambda gesture_id, pressed, ended: progress.append((gesture_id, pressed, ended)),
        modifier_mode="ctrl_alt",
        timer_factory=FakeTimer,
    )

    dispatcher.on_press(FakeKey(name="ctrl_l"))
    dispatcher.on_press(FakeKey(name="alt_l"))
    dispatcher.on_press(FakeKey(char="8"))
    dispatcher.on_release(FakeKey(char="8"))
    dispatcher.on_release(FakeKey(name="alt_l"))
    dispatcher.on_release(FakeKey(name="ctrl_l"))

    assert {gesture_id for gesture_id, _pressed, _ended in progress} == {1}
    assert progress[0] == (1, frozenset({"ctrl"}), False)
    assert progress[-1] == (1, frozenset(), True)
    assert triggers == [("english", "short", 1)]


def test_injected_keys_never_appear_in_gesture_progress() -> None:
    progress: list[tuple[int, frozenset[str], bool]] = []
    dispatcher = create_hotkey_dispatcher(
        {"english": {"hotkey": "ctrl+alt+8"}},
        lambda _action_id, _press_type, _gesture_id: None,
        on_progress=lambda gesture_id, pressed, ended: progress.append((gesture_id, pressed, ended)),
        modifier_mode="ctrl_alt",
        timer_factory=FakeTimer,
    )

    dispatcher.on_press(FakeKey(name="ctrl_l"), injected=True)
    dispatcher.on_press(FakeKey(name="alt_l"), injected=True)
    dispatcher.on_press(FakeKey(char="8"), injected=True)

    assert progress == []
