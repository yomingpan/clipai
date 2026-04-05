from __future__ import annotations

from types import SimpleNamespace

from clipai.platform.hotkey import LONG_PRESS_SEC, _HotkeyDispatcher, _normalize_key, expand_hotkeys


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


class _FakeTimer:
    def __init__(self, interval, callback) -> None:
        self.interval = interval
        self.callback = callback
        self.daemon = False
        self.started = False
        self.cancelled = False

    def start(self) -> None:
        self.started = True

    def cancel(self) -> None:
        self.cancelled = True

    def fire(self) -> None:
        if not self.cancelled:
            self.callback()


def test_hotkey_dispatcher_short_press_fires_only_short() -> None:
    events: list[tuple[str, str]] = []
    timers: list[_FakeTimer] = []

    dispatcher = _HotkeyDispatcher(
        [("summarize", {"ctrl", "alt", "5"})],
        lambda action_id, press_type: events.append((action_id, press_type)),
        long_press_sec=LONG_PRESS_SEC,
        timer_factory=lambda interval, callback: timers.append(_FakeTimer(interval, callback)) or timers[-1],
    )

    dispatcher.on_press(SimpleNamespace(name="ctrl_l"))
    dispatcher.on_press(SimpleNamespace(name="alt_l"))
    dispatcher.on_press(SimpleNamespace(vk=53))
    dispatcher.on_release(SimpleNamespace(vk=53))
    dispatcher.on_release(SimpleNamespace(name="alt_l"))
    dispatcher.on_release(SimpleNamespace(name="ctrl_l"))

    assert events == [("summarize", "short")]
    assert timers[0].interval == LONG_PRESS_SEC
    assert timers[0].cancelled is True


def test_hotkey_dispatcher_long_press_does_not_fire_short_on_release() -> None:
    events: list[tuple[str, str]] = []
    timers: list[_FakeTimer] = []

    dispatcher = _HotkeyDispatcher(
        [("summarize", {"ctrl", "alt", "5"})],
        lambda action_id, press_type: events.append((action_id, press_type)),
        timer_factory=lambda interval, callback: timers.append(_FakeTimer(interval, callback)) or timers[-1],
    )

    dispatcher.on_press(SimpleNamespace(name="ctrl_l"))
    dispatcher.on_press(SimpleNamespace(name="alt_l"))
    dispatcher.on_press(SimpleNamespace(vk=53))
    timers[0].fire()
    dispatcher.on_release(SimpleNamespace(vk=53))

    assert events == [("summarize", "long")]


def test_hotkey_dispatcher_keeps_actions_isolated() -> None:
    events: list[tuple[str, str]] = []
    timers: list[_FakeTimer] = []

    dispatcher = _HotkeyDispatcher(
        [
            ("action_1", {"ctrl", "alt", "1"}),
            ("action_2", {"ctrl", "alt", "2"}),
        ],
        lambda action_id, press_type: events.append((action_id, press_type)),
        timer_factory=lambda interval, callback: timers.append(_FakeTimer(interval, callback)) or timers[-1],
    )

    dispatcher.on_press(SimpleNamespace(name="ctrl_l"))
    dispatcher.on_press(SimpleNamespace(name="alt_l"))
    dispatcher.on_press(SimpleNamespace(vk=49))
    dispatcher.on_release(SimpleNamespace(vk=49))
    dispatcher.on_press(SimpleNamespace(vk=50))
    dispatcher.on_release(SimpleNamespace(vk=50))

    assert events == [("action_1", "short"), ("action_2", "short")]
