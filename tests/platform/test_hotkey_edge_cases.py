from __future__ import annotations

from dataclasses import dataclass
import logging

import pytest

from ClipAI.platform.hotkey import HotkeyListener, create_hotkey_dispatcher


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


class FakeListener:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


def setup_function() -> None:
    FakeTimer.timers.clear()


def make_dispatcher(events: list[tuple[str, str]], hotkey: str = "ctrl+alt+8"):
    return create_hotkey_dispatcher(
        {"explain_word": {"hotkey": hotkey}},
        lambda action_id, press_type: events.append((action_id, press_type)),
        modifier_mode="ctrl_alt",
        timer_factory=FakeTimer,
    )


def press_ctrl_alt_8(dispatcher) -> None:
    dispatcher.on_press(FakeKey(name="ctrl_l"))
    dispatcher.on_press(FakeKey(name="alt_l"))
    dispatcher.on_press(FakeKey(char="8"))


def release_ctrl_alt_8(dispatcher) -> None:
    dispatcher.on_release(FakeKey(char="8"))
    dispatcher.on_release(FakeKey(name="alt_l"))
    dispatcher.on_release(FakeKey(name="ctrl_l"))


def test_repeated_press_does_not_create_duplicate_timers_or_triggers() -> None:
    events: list[tuple[str, str]] = []
    dispatcher = make_dispatcher(events)

    dispatcher.on_press(FakeKey(name="ctrl_l"))
    dispatcher.on_press(FakeKey(name="alt_l"))
    dispatcher.on_press(FakeKey(char="8"))
    dispatcher.on_press(FakeKey(char="8"))
    dispatcher.on_press(FakeKey(char="8"))
    release_ctrl_alt_8(dispatcher)

    assert events == [("explain_word", "short")]
    assert len(FakeTimer.timers) == 1


def test_repeated_release_does_not_trigger_more_than_once() -> None:
    events: list[tuple[str, str]] = []
    dispatcher = make_dispatcher(events)

    press_ctrl_alt_8(dispatcher)
    dispatcher.on_release(FakeKey(char="8"))
    dispatcher.on_release(FakeKey(char="8"))
    dispatcher.on_release(FakeKey(name="alt_l"))
    dispatcher.on_release(FakeKey(name="ctrl_l"))

    assert events == [("explain_word", "short")]


def test_modifier_release_before_digit_cleans_active_state() -> None:
    events: list[tuple[str, str]] = []
    dispatcher = make_dispatcher(events)

    press_ctrl_alt_8(dispatcher)
    dispatcher.on_release(FakeKey(name="alt_l"))
    dispatcher.on_release(FakeKey(char="8"))
    dispatcher.on_release(FakeKey(name="ctrl_l"))
    dispatcher.on_release(FakeKey(char="8"))

    assert events == [("explain_word", "short")]


def test_action_waits_until_every_hotkey_key_is_released() -> None:
    events: list[tuple[str, str]] = []
    dispatcher = make_dispatcher(events)

    press_ctrl_alt_8(dispatcher)
    dispatcher.on_release(FakeKey(char="8"))
    dispatcher.on_release(FakeKey(name="alt_l"))
    assert events == []

    dispatcher.on_release(FakeKey(name="ctrl_l"))
    assert events == [("explain_word", "short")]


def test_shifted_digit_character_matches_configured_digit() -> None:
    events: list[tuple[str, str]] = []
    dispatcher = make_dispatcher(events, hotkey="ctrl+alt+1")

    dispatcher.on_press(FakeKey(name="ctrl_l"))
    dispatcher.on_press(FakeKey(name="alt_l"))
    dispatcher.on_press(FakeKey(char="!"))
    dispatcher.on_release(FakeKey(char="!"))
    dispatcher.on_release(FakeKey(name="alt_l"))
    dispatcher.on_release(FakeKey(name="ctrl_l"))

    assert events == [("explain_word", "short")]


def test_unknown_key_event_does_not_trigger_action() -> None:
    events: list[tuple[str, str]] = []
    dispatcher = make_dispatcher(events)

    dispatcher.on_press(FakeKey(name="ctrl_l"))
    dispatcher.on_press(FakeKey(name="alt_l"))
    dispatcher.on_press(FakeKey())
    dispatcher.on_release(FakeKey())
    dispatcher.on_release(FakeKey(name="alt_l"))
    dispatcher.on_release(FakeKey(name="ctrl_l"))

    assert events == []
    assert FakeTimer.timers == []


def test_fast_repeated_hotkey_presses_do_not_leave_stale_state() -> None:
    events: list[tuple[str, str]] = []
    dispatcher = make_dispatcher(events)

    press_ctrl_alt_8(dispatcher)
    release_ctrl_alt_8(dispatcher)
    press_ctrl_alt_8(dispatcher)
    release_ctrl_alt_8(dispatcher)

    assert events == [("explain_word", "short"), ("explain_word", "short")]
    assert len(FakeTimer.timers) == 2
    assert all(timer.cancelled for timer in FakeTimer.timers)


def test_timer_fire_then_release_does_not_trigger_short_after_long() -> None:
    events: list[tuple[str, str]] = []
    dispatcher = make_dispatcher(events)

    press_ctrl_alt_8(dispatcher)
    FakeTimer.timers[0].fire()
    release_ctrl_alt_8(dispatcher)

    assert events == [("explain_word", "long"), ("explain_word", "long_release")]


def test_injected_selection_copy_does_not_trigger_another_hotkey() -> None:
    events: list[tuple[str, str]] = []
    dispatcher = create_hotkey_dispatcher(
        {
            "english_companion": {"hotkey": "ctrl+alt+8"},
            "command_copilot": {"hotkey": "ctrl+alt+c"},
        },
        lambda action_id, press_type: events.append((action_id, press_type)),
        modifier_mode="ctrl_alt",
        timer_factory=FakeTimer,
    )

    press_ctrl_alt_8(dispatcher)
    FakeTimer.timers[0].fire()

    # Selection capture sends a synthetic Ctrl+C while the user's physical
    # Ctrl and Alt keys are still held for the original long press.
    dispatcher.on_press(FakeKey(name="ctrl_l"), injected=True)
    dispatcher.on_press(FakeKey(char="c"), injected=True)
    dispatcher.on_release(FakeKey(char="c"), injected=True)
    dispatcher.on_release(FakeKey(name="ctrl_l"), injected=True)

    release_ctrl_alt_8(dispatcher)

    assert events == [("english_companion", "long"), ("english_companion", "long_release")]
    assert len(FakeTimer.timers) == 1


def test_injected_keys_do_not_change_physical_hotkey_state_or_cancel(caplog) -> None:
    events: list[tuple[str, str]] = []
    dispatcher = create_hotkey_dispatcher(
        {"command_copilot": {"hotkey": "ctrl+alt+c"}},
        lambda action_id, press_type: events.append((action_id, press_type)),
        modifier_mode="ctrl_alt",
        timer_factory=FakeTimer,
        diagnostics_enabled=lambda flag: flag == "hotkey_raw_events",
    )

    with caplog.at_level(logging.DEBUG, logger="clipai.hotkey"):
        dispatcher.on_press(FakeKey(name="ctrl_l"), injected=True)
        dispatcher.on_press(FakeKey(name="alt_l"), injected=True)
        dispatcher.on_press(FakeKey(char="c"), injected=True)
        dispatcher.on_release(FakeKey(char="c"), injected=True)
        dispatcher.on_press(FakeKey(name="esc"), injected=True)
        dispatcher.on_release(FakeKey(name="alt_l"), injected=True)
        dispatcher.on_release(FakeKey(name="ctrl_l"), injected=True)

    assert events == []
    assert FakeTimer.timers == []
    assert "Ignored injected key press" in caplog.text
    assert "Ignored injected key release" in caplog.text

    dispatcher.on_press(FakeKey(name="ctrl_l"))
    dispatcher.on_press(FakeKey(name="alt_l"))
    dispatcher.on_press(FakeKey(char="c"))
    dispatcher.on_release(FakeKey(char="c"))
    dispatcher.on_release(FakeKey(name="alt_l"))
    dispatcher.on_release(FakeKey(name="ctrl_l"))

    assert events == [("command_copilot", "short")]


def test_release_then_timer_fire_does_not_trigger_long_after_short() -> None:
    events: list[tuple[str, str]] = []
    dispatcher = make_dispatcher(events)

    press_ctrl_alt_8(dispatcher)
    release_ctrl_alt_8(dispatcher)
    FakeTimer.timers[0].fire()

    assert events == [("explain_word", "short")]


def test_secure_desktop_transition_discards_stale_modifiers_before_next_key() -> None:
    events: list[tuple[str, str]] = []
    physical_modifiers = {"ctrl": True, "alt": True, "shift": False}
    dispatcher = create_hotkey_dispatcher(
        {"explain_word": {"hotkey": "ctrl+alt+8"}},
        lambda action_id, press_type: events.append((action_id, press_type)),
        modifier_mode="ctrl_alt",
        timer_factory=FakeTimer,
        key_is_pressed=physical_modifiers.get,
    )

    # Ctrl+Alt+Delete moves to the secure desktop, where the listener may not
    # receive releases for this in-progress chord.
    press_ctrl_alt_8(dispatcher)
    physical_modifiers["ctrl"] = False
    physical_modifiers["alt"] = False

    dispatcher.on_press(FakeKey(char="8"))
    dispatcher.on_release(FakeKey(char="8"))

    assert events == []
    assert FakeTimer.timers[0].cancelled is True

    # The next genuine shortcut still works after the stale state is cleared.
    physical_modifiers["ctrl"] = True
    dispatcher.on_press(FakeKey(name="ctrl_l"))
    physical_modifiers["alt"] = True
    dispatcher.on_press(FakeKey(name="alt_l"))
    dispatcher.on_press(FakeKey(char="8"))
    dispatcher.on_release(FakeKey(char="8"))
    physical_modifiers["alt"] = False
    dispatcher.on_release(FakeKey(name="alt_l"))
    physical_modifiers["ctrl"] = False
    dispatcher.on_release(FakeKey(name="ctrl_l"))

    assert events == [("explain_word", "short")]


def test_stale_cleanup_does_not_emit_invalid_for_the_revealing_key() -> None:
    events: list[tuple[str, str]] = []
    physical_keys = {"ctrl": True, "alt": True, "x": True, "b": False}
    dispatcher = create_hotkey_dispatcher(
        {"shorten": {"hotkey": "ctrl+alt+x"}},
        lambda action_id, press_type: events.append((action_id, press_type)),
        modifier_mode="ctrl_alt",
        timer_factory=FakeTimer,
        key_is_pressed=physical_keys.get,
    )

    dispatcher.on_press(FakeKey(name="ctrl_l"))
    dispatcher.on_press(FakeKey(name="alt_l"))
    dispatcher.on_press(FakeKey(char="x"))
    dispatcher.on_release(FakeKey(name="alt_l"))
    dispatcher.on_release(FakeKey(name="ctrl_l"))
    physical_keys["ctrl"] = False
    physical_keys["alt"] = False
    physical_keys["x"] = False
    physical_keys["b"] = True

    dispatcher.on_press(FakeKey(char="b"))

    assert events == []


@pytest.mark.parametrize("physical_x_state", [True, None])
def test_physical_or_unknown_key_state_preserves_active_lifecycle(
    physical_x_state: bool | None,
) -> None:
    events: list[tuple[str, str]] = []

    def key_is_pressed(token: str) -> bool | None:
        return physical_x_state if token == "x" else True

    dispatcher = create_hotkey_dispatcher(
        {
            "shorten": {"hotkey": "ctrl+alt+x"},
            "speech": {"hotkey": "ctrl+alt+q"},
        },
        lambda action_id, press_type: events.append((action_id, press_type)),
        modifier_mode="ctrl_alt",
        timer_factory=FakeTimer,
        key_is_pressed=key_is_pressed,
    )

    dispatcher.on_press(FakeKey(name="ctrl_l"))
    dispatcher.on_press(FakeKey(name="alt_l"))
    dispatcher.on_press(FakeKey(char="x"))
    active_timer = FakeTimer.timers[-1]
    dispatcher.on_press(FakeKey(char="q"))

    assert active_timer.cancelled is False
    active_timer.fire()
    assert events == [("shorten", "long")]


def test_listener_stop_calls_underlying_listener_and_marks_not_running() -> None:
    underlying = FakeListener()
    listener = HotkeyListener(underlying)

    listener.stop()

    assert listener.running is False
    assert underlying.stopped is True
