from __future__ import annotations

from dataclasses import dataclass

from ClipAI.core.commands import ShortcutTriggered, StartAction
from ClipAI.core.models import ShortcutDefinition
from ClipAI.platform.hotkey import create_hotkey_dispatcher
from ClipAI.services.shortcut_catalog import ShortcutCatalog
from ClipAI.services.shortcut_sequence import ShortcutSequenceCoordinator


@dataclass
class FakeKey:
    name: str | None = None
    char: str | None = None


class FakeTimer:
    def __init__(self, _delay, callback) -> None:
        self.callback = callback
        self.cancelled = False
        self.daemon = False

    def start(self) -> None:
        return None

    def cancel(self) -> None:
        self.cancelled = True

    def fire(self) -> None:
        if not self.cancelled:
            self.callback()


def test_stale_action_key_does_not_create_popup_during_speech_sequence() -> None:
    commands = []
    hotkey_timers: list[FakeTimer] = []
    physical_keys = {"ctrl": False, "alt": False, "x": False, "q": False, "6": False}
    catalog = ShortcutCatalog(
        [
            ShortcutDefinition("shorten", "ctrl+alt+x", "start_action", "shorten_content"),
            ShortcutDefinition("speech", "ctrl+alt+q", "speak_selection_or_clipboard"),
            ShortcutDefinition("explain", "ctrl+alt+6", "start_action", "explain_like_friend"),
        ]
    )
    sequence = ShortcutSequenceCoordinator(
        catalog,
        schedule=lambda delay, callback: FakeTimer(delay, callback),
    )

    def trigger(shortcut_id, press_type, _gesture_id) -> None:
        command = sequence.resolve(ShortcutTriggered(shortcut_id, press_type))
        if command is not None:
            commands.append(command)

    def timer_factory(delay, callback) -> FakeTimer:
        timer = FakeTimer(delay, callback)
        hotkey_timers.append(timer)
        return timer

    dispatcher = create_hotkey_dispatcher(
        {
            "shorten": {"hotkey": "ctrl+alt+x"},
            "speech": {"hotkey": "ctrl+alt+q"},
            "explain": {"hotkey": "ctrl+alt+6"},
        },
        trigger,
        modifier_mode="ctrl_alt",
        timer_factory=timer_factory,
        key_is_pressed=physical_keys.get,
    )

    def press(token: str, key: FakeKey) -> None:
        physical_keys[token] = True
        dispatcher.on_press(key)

    def release(token: str, key: FakeKey) -> None:
        physical_keys[token] = False
        dispatcher.on_release(key)

    press("ctrl", FakeKey(name="ctrl_l"))
    press("alt", FakeKey(name="alt_l"))
    press("x", FakeKey(char="x"))
    release("alt", FakeKey(name="alt_l"))
    release("ctrl", FakeKey(name="ctrl_l"))
    physical_keys["x"] = False  # The OS saw X-up, but the listener missed it.

    press("ctrl", FakeKey(name="ctrl_l"))
    press("alt", FakeKey(name="alt_l"))
    press("q", FakeKey(char="q"))
    for timer in tuple(hotkey_timers):
        timer.fire()
    press("6", FakeKey(char="6"))
    release("6", FakeKey(char="6"))
    assert commands == [StartAction("explain_like_friend", "short", "speech")]

    release("q", FakeKey(char="q"))
    release("alt", FakeKey(name="alt_l"))
    release("ctrl", FakeKey(name="ctrl_l"))

    assert commands == [StartAction("explain_like_friend", "short", "speech")]
