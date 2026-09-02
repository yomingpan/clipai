import ctypes
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from ClipAI.core.commands import (
    EntryPanelDigitPressed,
    InterruptionRequested,
    OpenUnifiedEntryPanel,
    ShortcutPressEnded,
    ShortcutPressInvoked,
    ShortcutPressStarted,
)
from ClipAI.core.models import ModifierHoldId
from ClipAI.platform import keyboard_state
from ClipAI.platform.hotkey import create_hotkey_dispatcher


class Key:
    def __init__(
        self,
        name: str | None = None,
        *,
        char: str | None = None,
        vk: int | None = None,
    ) -> None:
        self.name = name
        self.char = char
        self.vk = vk


class Timer:
    timers: list["Timer"] = []

    def __init__(self, delay, callback) -> None:
        self.delay = delay
        self.callback = callback
        self.cancelled = False
        self.daemon = False
        self.__class__.timers.append(self)

    def start(self) -> None:
        pass

    def cancel(self) -> None:
        self.cancelled = True

    def fire(self) -> None:
        if not self.cancelled:
            self.callback()


def _dispatcher(events, shortcuts=None):
    Timer.timers.clear()
    return create_hotkey_dispatcher(
        shortcuts or {},
        events.append,
        modifier_mode="ctrl_alt",
        timer_factory=Timer,
        entry_panel_enabled=True,
    )


def _key_for_token(token: str) -> Key:
    return Key(char=token) if len(token) == 1 else Key(token)


def test_exact_alt_hold_opens_entry_panel_at_500_ms_deadline() -> None:
    Timer.timers.clear()
    events = []
    dispatcher = create_hotkey_dispatcher(
        {},
        events.append,
        modifier_mode="ctrl_alt",
        timer_factory=Timer,
        entry_panel_enabled=True,
    )

    dispatcher.on_press(Key("alt"))
    assert Timer.timers[0].delay == 0.5
    Timer.timers[0].fire()

    assert events == [OpenUnifiedEntryPanel(ModifierHoldId(1))]


def test_repeated_side_alt_keydown_preserves_hold_until_deadline(monkeypatch) -> None:
    class FakeUser32:
        def GetAsyncKeyState(self, virtual_key: int) -> int:
            return 0x8000 if virtual_key == 0xA4 else 0

    monkeypatch.setattr(keyboard_state.sys, "platform", "win32")
    monkeypatch.setattr(
        ctypes,
        "windll",
        SimpleNamespace(user32=FakeUser32()),
        raising=False,
    )
    Timer.timers.clear()
    events = []
    dispatcher = create_hotkey_dispatcher(
        {},
        events.append,
        timer_factory=Timer,
        key_is_pressed=keyboard_state.windows_key_is_pressed,
        entry_panel_enabled=True,
    )

    dispatcher.on_press(Key("alt"))
    timer = Timer.timers[0]
    for _ in range(3):
        dispatcher.on_press(Key("alt"))
    timer.fire()

    assert events == [OpenUnifiedEntryPanel(ModifierHoldId(1))]


def test_ctrl_alt_chord_does_not_open_entry_panel() -> None:
    Timer.timers.clear()
    events = []
    dispatcher = create_hotkey_dispatcher(
        {},
        events.append,
        modifier_mode="ctrl_alt",
        timer_factory=Timer,
        entry_panel_enabled=True,
    )

    dispatcher.on_press(Key("alt"))
    timer = Timer.timers[0]
    dispatcher.on_press(Key("ctrl"))
    timer.callback()

    assert timer.cancelled is True
    assert events == []


def test_ctrl_then_alt_never_starts_the_exact_alt_hold() -> None:
    Timer.timers.clear()
    events = []
    dispatcher = create_hotkey_dispatcher(
        {},
        events.append,
        modifier_mode="ctrl_alt",
        timer_factory=Timer,
        entry_panel_enabled=True,
    )

    dispatcher.on_press(Key("ctrl"))
    dispatcher.on_press(Key("alt"))

    assert Timer.timers == []
    assert events == []


def test_digit_after_panel_open_is_claimed_instead_of_invoking_direct_shortcut() -> None:
    Timer.timers.clear()
    events = []
    dispatcher = create_hotkey_dispatcher(
        {"english": {"hotkey": "ctrl+alt+8"}},
        events.append,
        modifier_mode="ctrl_alt",
        timer_factory=Timer,
        entry_panel_enabled=True,
    )
    dispatcher.on_press(Key("alt"))
    Timer.timers[0].fire()

    dispatcher.on_press(Key("8"))

    assert events == [
        OpenUnifiedEntryPanel(ModifierHoldId(1)),
        EntryPanelDigitPressed(ModifierHoldId(1), "8"),
    ]
    assert len(Timer.timers) == 1


def test_open_panel_keeps_digit_claim_when_ctrl_joins_held_alt() -> None:
    Timer.timers.clear()
    events = []
    dispatcher = create_hotkey_dispatcher(
        {"english": {"hotkey": "ctrl+alt+8"}},
        events.append,
        modifier_mode="ctrl_alt",
        timer_factory=Timer,
        entry_panel_enabled=True,
    )
    dispatcher.on_press(Key("alt"))
    Timer.timers[0].fire()

    dispatcher.on_press(Key("ctrl"))
    dispatcher.on_press(Key("8"))

    assert events == [
        OpenUnifiedEntryPanel(ModifierHoldId(1)),
        EntryPanelDigitPressed(ModifierHoldId(1), "8"),
    ]
    assert len(Timer.timers) == 1


def test_ctrl_alt_digit_preserves_direct_shortcut_without_starting_panel_hold() -> None:
    Timer.timers.clear()
    events = []
    dispatcher = create_hotkey_dispatcher(
        {"english": {"hotkey": "ctrl+alt+8"}},
        events.append,
        modifier_mode="ctrl_alt",
        timer_factory=Timer,
        entry_panel_enabled=True,
    )
    dispatcher.on_press(Key("ctrl"))
    dispatcher.on_press(Key("alt"))
    assert Timer.timers == []

    dispatcher.on_press(Key("8"))
    dispatcher.on_release(Key("8"))

    assert Timer.timers[0].cancelled is True
    assert events == [
        ShortcutPressStarted(1, "english"),
        ShortcutPressInvoked(1, "english", "short"),
        ShortcutPressEnded(1, "english", "released"),
    ]


def test_release_before_deadline_invalidates_even_queued_timer_callback() -> None:
    Timer.timers.clear()
    events = []
    dispatcher = create_hotkey_dispatcher(
        {},
        events.append,
        timer_factory=Timer,
        entry_panel_enabled=True,
    )
    dispatcher.on_press(Key("alt"))
    timer = Timer.timers[0]

    dispatcher.on_release(Key("alt"))
    timer.callback()

    assert timer.cancelled is True
    assert events == []


def test_hold_deadline_uses_listener_alt_state_when_windows_poll_is_false() -> None:
    Timer.timers.clear()
    events = []
    dispatcher = create_hotkey_dispatcher(
        {},
        events.append,
        timer_factory=Timer,
        # Windows can report a false negative for Alt from inside its
        # low-level keyboard hook. The listener's matching press/release
        # lifecycle remains authoritative for this non-side-effecting open.
        key_is_pressed=lambda _token: False,
        entry_panel_enabled=True,
    )
    dispatcher.on_press(Key("alt"))

    Timer.timers[0].callback()

    assert events == [OpenUnifiedEntryPanel(ModifierHoldId(1))]


def test_repeated_alt_keydown_preserves_hold_when_windows_poll_is_false() -> None:
    Timer.timers.clear()
    events = []
    dispatcher = create_hotkey_dispatcher(
        {},
        events.append,
        timer_factory=Timer,
        key_is_pressed=lambda _token: False,
        entry_panel_enabled=True,
    )

    dispatcher.on_press(Key("alt"))
    timer = Timer.timers[0]
    for _ in range(5):
        dispatcher.on_press(Key("alt"))
    timer.fire()

    assert events == [OpenUnifiedEntryPanel(ModifierHoldId(1))]


def test_alt_auto_repeat_after_panel_open_does_not_start_a_second_hold() -> None:
    Timer.timers.clear()
    events = []
    dispatcher = create_hotkey_dispatcher(
        {},
        events.append,
        timer_factory=Timer,
        key_is_pressed=lambda _token: False,
        entry_panel_enabled=True,
    )

    dispatcher.on_press(Key("alt"))
    Timer.timers[0].fire()
    for _ in range(5):
        dispatcher.on_press(Key("alt"))

    assert len(Timer.timers) == 1
    assert events == [OpenUnifiedEntryPanel(ModifierHoldId(1))]


def test_exact_alt_hold_does_not_open_before_500_ms_deadline() -> None:
    events = []
    dispatcher = _dispatcher(events)

    dispatcher.on_press(Key("alt"))

    assert Timer.timers[0].delay == 0.5
    assert events == []


@pytest.mark.parametrize("alt_name", ["alt", "alt_l", "alt_r"])
def test_left_and_right_alt_share_the_exact_alt_contract(alt_name: str) -> None:
    events = []
    dispatcher = _dispatcher(events)

    dispatcher.on_press(Key(alt_name))
    Timer.timers[0].fire()

    assert events == [OpenUnifiedEntryPanel(ModifierHoldId(1))]


@pytest.mark.parametrize(
    ("joined_key", "release_key"),
    [
        (Key("tab"), Key("tab")),
        (Key("f4"), Key("f4")),
        (Key("space"), Key("space")),
        (Key("esc"), Key("esc")),
        (Key("shift"), Key("shift")),
        (Key("cmd"), Key("cmd")),
    ],
    ids=["alt-tab", "alt-f4", "alt-space", "alt-esc", "shift-alt", "win-alt"],
)
def test_native_alt_combinations_cancel_only_the_panel_candidate(
    joined_key: Key,
    release_key: Key,
) -> None:
    events = []
    dispatcher = _dispatcher(events)

    dispatcher.on_press(Key("alt"))
    timer = Timer.timers[0]
    dispatcher.on_press(joined_key)
    timer.callback()
    dispatcher.on_release(release_key)
    dispatcher.on_release(Key("alt"))

    assert timer.cancelled is True
    assert OpenUnifiedEntryPanel(ModifierHoldId(1)) not in events
    assert not any(isinstance(event, InterruptionRequested) for event in events)


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (Key("tab"), Key("alt")),
        (Key("f4"), Key("alt")),
        (Key("space"), Key("alt")),
        (Key("shift"), Key("alt")),
        (Key("cmd"), Key("alt")),
    ],
    ids=["tab-alt", "f4-alt", "space-alt", "shift-alt", "win-alt"],
)
def test_existing_key_then_alt_never_starts_an_exact_alt_hold(
    first: Key,
    second: Key,
) -> None:
    events = []
    dispatcher = _dispatcher(events)

    dispatcher.on_press(first)
    dispatcher.on_press(second)

    assert Timer.timers == []
    assert not any(isinstance(event, OpenUnifiedEntryPanel) for event in events)


@pytest.mark.parametrize(
    "sequence",
    [
        (Key("alt_gr"),),
        (Key("ctrl_r"), Key("alt_gr")),
        (Key("alt_gr"), Key("ctrl_r")),
    ],
    ids=["altgr-alone", "ctrl-altgr", "altgr-ctrl"],
)
def test_altgr_never_becomes_an_exact_alt_panel_hold(sequence: tuple[Key, ...]) -> None:
    events = []
    dispatcher = _dispatcher(events)

    for key in sequence:
        dispatcher.on_press(key)

    assert Timer.timers == []
    assert not any(isinstance(event, OpenUnifiedEntryPanel) for event in events)


def test_every_configured_ctrl_alt_shortcut_keeps_its_existing_lifecycle() -> None:
    config = yaml.safe_load(Path("config/shortcuts.yaml").read_text(encoding="utf-8"))
    definitions = config["shortcuts"]
    shortcuts = {
        definition["id"]: {"hotkey": definition["hotkey"]}
        for definition in definitions
    }

    for definition in definitions:
        Timer.timers.clear()
        events = []
        dispatcher = create_hotkey_dispatcher(
            shortcuts,
            events.append,
            modifier_mode="ctrl_alt",
            timer_factory=Timer,
            entry_panel_enabled=True,
        )
        trigger = definition["hotkey"].split("+")[-1]
        dispatcher.on_press(Key("ctrl"))
        dispatcher.on_press(Key("alt"))
        dispatcher.on_press(_key_for_token(trigger))
        dispatcher.on_release(_key_for_token(trigger))

        assert events == [
            ShortcutPressStarted(1, definition["id"]),
            ShortcutPressInvoked(1, definition["id"], "short"),
            ShortcutPressEnded(1, definition["id"], "released"),
        ], definition["id"]


@pytest.mark.parametrize("digit", list("0123456789"))
def test_configured_ctrl_alt_digit_accepts_numpad_virtual_keys(digit: str) -> None:
    events = []
    dispatcher = _dispatcher(
        events,
        {f"action-{digit}": {"hotkey": f"ctrl+alt+{digit}"}},
    )

    dispatcher.on_press(Key("ctrl"))
    dispatcher.on_press(Key("alt"))
    numpad = Key(vk=96 + int(digit))
    dispatcher.on_press(numpad)
    dispatcher.on_release(numpad)

    assert events == [
        ShortcutPressStarted(1, f"action-{digit}"),
        ShortcutPressInvoked(1, f"action-{digit}", "short"),
        ShortcutPressEnded(1, f"action-{digit}", "released"),
    ]


def test_panel_settlement_allows_fresh_hold_after_a_missing_release() -> None:
    Timer.timers.clear()
    events = []
    dispatcher = create_hotkey_dispatcher(
        {},
        events.append,
        timer_factory=Timer,
        key_is_pressed=lambda _token: False,
        entry_panel_enabled=True,
    )

    dispatcher.on_press(Key("alt"))
    Timer.timers[0].fire()
    dispatcher.settle_entry_panel_hold(ModifierHoldId(1))
    dispatcher.on_press(Key("alt"))
    Timer.timers[1].fire()

    assert events == [
        OpenUnifiedEntryPanel(ModifierHoldId(1)),
        OpenUnifiedEntryPanel(ModifierHoldId(2)),
    ]


def test_open_panel_keeps_alt_digit_claim_when_windows_poll_is_false() -> None:
    Timer.timers.clear()
    events = []
    dispatcher = create_hotkey_dispatcher(
        {},
        events.append,
        timer_factory=Timer,
        key_is_pressed=lambda _token: False,
        entry_panel_enabled=True,
    )

    dispatcher.on_press(Key("alt"))
    Timer.timers[0].fire()
    dispatcher.on_press(Key("8"))

    assert events == [
        OpenUnifiedEntryPanel(ModifierHoldId(1)),
        EntryPanelDigitPressed(ModifierHoldId(1), "8"),
    ]


def test_unbound_stale_characters_do_not_block_a_later_panel_hold() -> None:
    Timer.timers.clear()
    events = []
    physical = {"alt": True}
    dispatcher = create_hotkey_dispatcher(
        {},
        events.append,
        timer_factory=Timer,
        key_is_pressed=physical.get,
        entry_panel_enabled=True,
    )

    # Matches the incident log: the global hook saw normal characters but
    # missed their releases. Windows cannot query these character states.
    dispatcher.on_press(Key(char="+"))
    dispatcher.on_press(Key(char=":"))
    dispatcher.on_press(Key(char="v"))
    dispatcher.on_press(Key("alt"))
    Timer.timers[0].fire()

    assert events == [OpenUnifiedEntryPanel(ModifierHoldId(1))]


def test_numpad_digit_is_claimed_by_open_panel_hold() -> None:
    Timer.timers.clear()
    events = []
    dispatcher = create_hotkey_dispatcher(
        {"english": {"hotkey": "ctrl+alt+8"}},
        events.append,
        timer_factory=Timer,
        entry_panel_enabled=True,
    )
    dispatcher.on_press(Key("alt"))
    Timer.timers[0].fire()

    dispatcher.on_press(Key(vk=104))

    assert events[-1] == EntryPanelDigitPressed(ModifierHoldId(1), "8")
    assert len(Timer.timers) == 1


def test_shutdown_cancels_panel_hold_and_blocks_late_callback() -> None:
    Timer.timers.clear()
    events = []
    dispatcher = create_hotkey_dispatcher(
        {},
        events.append,
        timer_factory=Timer,
        entry_panel_enabled=True,
    )
    dispatcher.on_press(Key("alt"))
    timer = Timer.timers[0]

    dispatcher.stop()
    timer.callback()

    assert timer.cancelled is True
    assert events == []
