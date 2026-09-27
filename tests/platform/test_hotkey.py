from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from ClipAI.core.commands import InterruptionRequested, ShortcutKeyStateChanged, ShortcutPressInvoked, ShortcutPressStarted
from ClipAI.platform.hotkey import (
    _WindowsHotkeyEventFilter,
    create_hotkey_dispatcher,
    expand_hotkeys,
    register_hotkeys_with_long_press,
)


def test_inline_hotkey_m_is_suppressed_without_swallowing_normal_typing() -> None:
    events = []
    dispatcher = create_hotkey_dispatcher(
        {"inline": {"hotkey": "ctrl+alt+m"}}, events.append,
        modifier_mode="ctrl_alt", timer_factory=FakeTimer,
    )
    pressed = {"ctrl": False, "alt": False}
    event_filter = _WindowsHotkeyEventFilter(
        dispatcher, suppressible_m=True, key_is_pressed=lambda key: pressed[key],
    )

    class Suppressed(Exception):
        pass

    class Listener:
        _WM_PROCESS = 0x410

        def __init__(self) -> None:
            self.posted = []
            self._message_loop = SimpleNamespace(post=lambda *args: self.posted.append(args))

        def suppress_event(self) -> None:
            raise Suppressed

    listener = Listener()
    event_filter.bind_listener(listener)
    down = SimpleNamespace(vkCode=0x4D, flags=0)
    assert event_filter(0x0100, down) is True
    assert listener.posted == []
    pressed.update(ctrl=True, alt=True)
    with pytest.raises(Suppressed):
        event_filter(0x0100, down)
    with pytest.raises(Suppressed):
        event_filter(0x0100, down)  # repeat while held
    pressed.update(ctrl=False, alt=False)
    with pytest.raises(Suppressed):
        event_filter(0x0101, down)
    assert listener.posted == [
        (0x410, 0x0100, 0x4D), (0x410, 0x0100, 0x4D), (0x410, 0x0101, 0x4D),
    ]
    assert event_filter(0x0100, down) is True
    dispatcher.on_press(FakeKey(name="ctrl_l"))
    dispatcher.on_press(FakeKey(name="alt_l"))
    for _, message, vk in listener.posted:
        (dispatcher.on_press if message == 0x0100 else dispatcher.on_release)(FakeKey(vk=vk))
    assert len([event for event in events if isinstance(event, ShortcutPressStarted)]) == 1
    assert len([event for event in events if isinstance(event, ShortcutPressInvoked)]) == 1
    assert event_filter(0x0100, SimpleNamespace(vkCode=0x4D, flags=0x10)) is False


def test_inline_hotkey_uses_native_alt_flag_when_async_alt_state_lags() -> None:
    dispatcher = create_hotkey_dispatcher(
        {"inline": {"hotkey": "ctrl+alt+m"}}, lambda _event: None,
        modifier_mode="ctrl_alt", timer_factory=FakeTimer,
    )
    event_filter = _WindowsHotkeyEventFilter(
        dispatcher, suppressible_m=True,
        key_is_pressed=lambda key: key == "ctrl",
    )

    class Suppressed(Exception):
        pass

    listener = SimpleNamespace(
        _WM_PROCESS=0x410,
        _message_loop=SimpleNamespace(post=lambda *_args: None),
        suppress_event=lambda: (_ for _ in ()).throw(Suppressed()),
    )
    event_filter.bind_listener(listener)
    with pytest.raises(Suppressed):
        event_filter(0x0104, SimpleNamespace(vkCode=0x4D, flags=0x20))


def test_inline_escape_is_consumed_only_during_owned_interaction() -> None:
    events = []
    dispatcher = create_hotkey_dispatcher({}, events.append, timer_factory=FakeTimer)
    owner = {"active": False}
    modifiers = {"ctrl": False, "alt": False, "shift": False}
    event_filter = _WindowsHotkeyEventFilter(
        dispatcher,
        inline_escape_owner=lambda: owner["active"],
        key_is_pressed=lambda key: modifiers[key],
    )

    class Suppressed(Exception):
        pass

    posted = []
    event_filter.bind_listener(SimpleNamespace(
        _WM_PROCESS=0x410,
        _message_loop=SimpleNamespace(post=lambda *args: posted.append(args)),
        suppress_event=lambda: (_ for _ in ()).throw(Suppressed()),
    ))
    escape = SimpleNamespace(vkCode=0x1B, flags=0)
    assert event_filter(0x0100, escape) is True
    owner["active"] = True
    modifiers["ctrl"] = True
    assert event_filter(0x0100, escape) is True
    modifiers["ctrl"] = False
    with pytest.raises(Suppressed):
        event_filter(0x0100, escape)
    owner["active"] = False  # cancellation can settle before physical release
    with pytest.raises(Suppressed):
        event_filter(0x0101, escape)
    assert posted == [(0x410, 0x0100, 0x1B), (0x410, 0x0101, 0x1B)]
    dispatcher.on_press(FakeKey(name="esc"))
    dispatcher.on_release(FakeKey(name="esc"))
    assert len([event for event in events if isinstance(event, InterruptionRequested)]) == 1
    assert event_filter(0x0100, escape) is True


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


def semantic_recorder(events):
    def record(event) -> None:
        if isinstance(event, ShortcutPressInvoked):
            events.append((event.shortcut_id, event.press_type))
        elif isinstance(event, InterruptionRequested):
            events.append(("", f"interrupt_{event.scope}"))

    return record


def test_expand_hotkeys_adds_default_modifier_prefix() -> None:
    assert expand_hotkeys("8", modifier_mode="ctrl_alt") == ["ctrl+alt+8"]


def test_short_press_triggers_action_once() -> None:
    events: list[tuple[str, str]] = []
    dispatcher = create_hotkey_dispatcher(
        {"explain_word": {"hotkey": "ctrl+alt+8"}},
        semantic_recorder(events),
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


def test_short_press_matches_action_key_release_by_virtual_key() -> None:
    events: list[tuple[str, str]] = []
    dispatcher = create_hotkey_dispatcher(
        {"speech": {"hotkey": "ctrl+alt+q"}},
        semantic_recorder(events),
        modifier_mode="ctrl_alt",
        timer_factory=FakeTimer,
    )

    dispatcher.on_press(FakeKey(name="ctrl_l"))
    dispatcher.on_press(FakeKey(name="alt_l"))
    dispatcher.on_press(FakeKey(char="q", vk=0x51))
    dispatcher.on_release(FakeKey(char="\x11", vk=0x51))
    FakeTimer.timers[0].fire()

    assert events == [("speech", "short")]


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
        semantic_recorder(events),
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
        semantic_recorder(events),
        modifier_mode="ctrl_alt",
        timer_factory=FakeTimer,
    )

    dispatcher.on_press(FakeKey(name="ctrl_l"))
    dispatcher.on_press(FakeKey(name="alt_l"))
    dispatcher.on_press(FakeKey(char="8"))
    FakeTimer.timers[0].fire()
    assert events == [("explain_word", "long")]
    dispatcher.on_release(FakeKey(char="8"))
    assert events == [("explain_word", "long")]
    dispatcher.on_release(FakeKey(name="alt_l"))
    dispatcher.on_release(FakeKey(name="ctrl_l"))

    assert events == [("explain_word", "long")]


def test_escape_interrupts_current_immediately_then_escalates_after_threshold() -> None:
    events: list[tuple[str, str]] = []
    dispatcher = create_hotkey_dispatcher(
        {},
        semantic_recorder(events),
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
        lambda event: events.append(f"interrupt_{event.scope}") if isinstance(event, InterruptionRequested) else None,
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
        semantic_recorder(events),
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

    assert events == [("speech", "long"), ("friend", "short")]


def test_observation_reports_key_state_and_active_press_identity() -> None:
    events = []
    dispatcher = create_hotkey_dispatcher(
        {"english": {"hotkey": "ctrl+alt+8"}},
        events.append,
        modifier_mode="ctrl_alt",
        timer_factory=FakeTimer,
    )
    lease = dispatcher.observe()

    dispatcher.on_press(FakeKey(name="ctrl_l"))
    dispatcher.on_press(FakeKey(name="alt_l"))
    dispatcher.on_press(FakeKey(char="8"))
    dispatcher.on_release(FakeKey(char="8"))
    dispatcher.on_release(FakeKey(name="alt_l"))
    dispatcher.on_release(FakeKey(name="ctrl_l"))

    key_states = [event.pressed_keys for event in events if isinstance(event, ShortcutKeyStateChanged)]
    starts = [event for event in events if isinstance(event, ShortcutPressStarted)]
    assert lease.snapshot.pressed_keys == frozenset()
    assert key_states[0] == frozenset({"ctrl"})
    assert key_states[-1] == frozenset()
    assert len(starts) == 1


def test_injected_keys_never_appear_in_observation() -> None:
    events = []
    dispatcher = create_hotkey_dispatcher(
        {"english": {"hotkey": "ctrl+alt+8"}},
        events.append,
        modifier_mode="ctrl_alt",
        timer_factory=FakeTimer,
    )
    dispatcher.observe()

    dispatcher.on_press(FakeKey(name="ctrl_l"), injected=True)
    dispatcher.on_press(FakeKey(name="alt_l"), injected=True)
    dispatcher.on_press(FakeKey(char="8"), injected=True)

    assert events == []


def test_registered_windows_listener_filters_injected_keys_before_dispatch(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class Listener:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

        def start(self) -> None:
            captured["started"] = True

        def stop(self) -> None:
            pass

    monkeypatch.setattr("pynput.keyboard.Listener", Listener)

    register_hotkeys_with_long_press(
        {"copilot": {"hotkey": "ctrl+alt+c"}},
        lambda _event: None,
        modifier_mode="ctrl_alt",
    )

    event_filter = captured["win32_event_filter"]
    assert callable(event_filter)
    assert event_filter(0, SimpleNamespace(flags=0x10)) is False
    assert event_filter(0, SimpleNamespace(flags=0)) is True
    assert captured["started"] is True
