from ClipAI.core.commands import (
    EntryPanelDigitPressed,
    OpenUnifiedEntryPanel,
    ShortcutPressEnded,
    ShortcutPressInvoked,
    ShortcutPressStarted,
)
from ClipAI.core.models import ModifierHoldId
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


def test_exact_ctrl_alt_hold_opens_entry_panel_at_deadline() -> None:
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
    assert Timer.timers[0].delay == 1.5
    Timer.timers[0].fire()

    assert events == [OpenUnifiedEntryPanel(ModifierHoldId(1))]


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
    dispatcher.on_press(Key("ctrl"))
    dispatcher.on_press(Key("alt"))
    Timer.timers[0].fire()

    dispatcher.on_press(Key("8"))

    assert events == [
        OpenUnifiedEntryPanel(ModifierHoldId(1)),
        EntryPanelDigitPressed(ModifierHoldId(1), "8"),
    ]
    assert len(Timer.timers) == 1


def test_digit_before_hold_deadline_preserves_direct_shortcut() -> None:
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
    dispatcher.on_press(Key("ctrl"))
    dispatcher.on_press(Key("alt"))
    timer = Timer.timers[0]

    dispatcher.on_release(Key("alt"))
    timer.callback()

    assert timer.cancelled is True
    assert events == []


def test_hold_deadline_rechecks_physical_modifier_state() -> None:
    Timer.timers.clear()
    events = []
    physical = {"ctrl": True, "alt": True}
    dispatcher = create_hotkey_dispatcher(
        {},
        events.append,
        timer_factory=Timer,
        key_is_pressed=physical.get,
        entry_panel_enabled=True,
    )
    dispatcher.on_press(Key("ctrl"))
    dispatcher.on_press(Key("alt"))

    physical["alt"] = False
    Timer.timers[0].callback()

    assert events == []


def test_unbound_stale_characters_do_not_block_a_later_panel_hold() -> None:
    Timer.timers.clear()
    events = []
    physical = {"ctrl": True, "alt": True}
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
    dispatcher.on_press(Key("ctrl"))
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
    dispatcher.on_press(Key("ctrl"))
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
    dispatcher.on_press(Key("ctrl"))
    dispatcher.on_press(Key("alt"))
    timer = Timer.timers[0]

    dispatcher.stop()
    timer.callback()

    assert timer.cancelled is True
    assert events == []
