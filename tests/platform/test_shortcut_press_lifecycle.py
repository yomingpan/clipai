from ClipAI.core.commands import (
    InterruptionRequested,
    ShortcutKeyStateChanged,
    ShortcutPressEnded,
    ShortcutPressInvoked,
    ShortcutPressStarted,
)
from ClipAI.platform.hotkey import create_hotkey_dispatcher


class Key:
    def __init__(self, name: str) -> None:
        self.name = name


class Timer:
    def __init__(self, _delay, callback) -> None:
        self.callback = callback
        self.cancelled = False
        self.daemon = False

    def start(self) -> None:
        pass

    def cancel(self) -> None:
        self.cancelled = True


def test_each_function_key_press_gets_a_new_identity_while_modifiers_remain_held() -> None:
    events = []
    dispatcher = create_hotkey_dispatcher(
        {"english": {"hotkey": "ctrl+alt+8"}},
        events.append,
        modifier_mode="ctrl_alt",
    )

    dispatcher.on_press(Key("ctrl"))
    dispatcher.on_press(Key("alt"))
    dispatcher.on_press(Key("8"))
    dispatcher.on_release(Key("8"))
    dispatcher.on_press(Key("8"))
    dispatcher.on_release(Key("8"))

    starts = [event for event in events if isinstance(event, ShortcutPressStarted)]
    invoked = [event for event in events if isinstance(event, ShortcutPressInvoked)]
    ended = [event for event in events if isinstance(event, ShortcutPressEnded)]

    assert [event.shortcut_id for event in starts] == ["english", "english"]
    assert starts[0].press_id != starts[1].press_id
    assert [event.press_id for event in invoked] == [event.press_id for event in starts]
    assert [event.press_id for event in ended] == [event.press_id for event in starts]
    assert [event.press_type for event in invoked] == ["short", "short"]
    assert [event.outcome for event in ended] == ["released", "released"]


def test_held_speech_composer_and_action_have_independent_press_identities() -> None:
    events = []
    dispatcher = create_hotkey_dispatcher(
        {
            "speech": {"hotkey": "ctrl+alt+q"},
            "english": {"hotkey": "ctrl+alt+6"},
        },
        events.append,
        modifier_mode="ctrl_alt",
        timer_factory=Timer,
    )

    dispatcher.on_press(Key("ctrl"))
    dispatcher.on_press(Key("alt"))
    dispatcher.on_press(Key("q"))
    dispatcher.on_press(Key("6"))

    starts = [event for event in events if isinstance(event, ShortcutPressStarted)]
    snapshot = dispatcher.observe().snapshot
    assert [event.shortcut_id for event in starts] == ["speech", "english"]
    assert starts[0].press_id != starts[1].press_id
    assert [(press.press_id, press.shortcut_id) for press in snapshot.active_presses] == [
        (starts[0].press_id, "speech"),
        (starts[1].press_id, "english"),
    ]


def test_stale_recovery_cancels_the_exact_active_press() -> None:
    events = []
    physical = {"ctrl": True, "alt": True, "8": True, "x": True}
    dispatcher = create_hotkey_dispatcher(
        {"english": {"hotkey": "ctrl+alt+8"}},
        events.append,
        modifier_mode="ctrl_alt",
        timer_factory=Timer,
        key_is_pressed=physical.get,
    )
    dispatcher.on_press(Key("ctrl"))
    dispatcher.on_press(Key("alt"))
    dispatcher.on_press(Key("8"))
    started = next(event for event in events if isinstance(event, ShortcutPressStarted))

    physical["ctrl"] = False
    dispatcher.on_press(Key("x"))

    terminal = [event for event in events if isinstance(event, ShortcutPressEnded)]
    assert terminal == [
        ShortcutPressEnded(started.press_id, "english", "cancelled")
    ]


def test_long_press_deadline_cancels_when_action_key_is_physically_released() -> None:
    events = []
    timers = []
    physical = {"ctrl": True, "alt": True, "q": True}

    def timer_factory(delay, callback):
        timer = Timer(delay, callback)
        timers.append(timer)
        return timer

    dispatcher = create_hotkey_dispatcher(
        {"speech": {"hotkey": "ctrl+alt+q"}},
        events.append,
        modifier_mode="ctrl_alt",
        timer_factory=timer_factory,
        key_is_pressed=physical.get,
    )
    dispatcher.on_press(Key("ctrl"))
    dispatcher.on_press(Key("alt"))
    dispatcher.on_press(Key("q"))
    started = next(event for event in events if isinstance(event, ShortcutPressStarted))

    physical["q"] = False
    timers[0].callback()

    lifecycle = [
        event
        for event in events
        if isinstance(event, (ShortcutPressInvoked, ShortcutPressEnded))
    ]
    assert lifecycle == [
        ShortcutPressEnded(started.press_id, "speech", "cancelled")
    ]


def test_observation_close_stops_key_events_but_not_terminal_lifecycle() -> None:
    events = []
    dispatcher = create_hotkey_dispatcher(
        {"english": {"hotkey": "ctrl+alt+8"}},
        events.append,
        modifier_mode="ctrl_alt",
        timer_factory=Timer,
    )
    lease = dispatcher.observe()
    dispatcher.on_press(Key("ctrl"))
    dispatcher.on_press(Key("alt"))
    dispatcher.on_press(Key("8"))
    key_event_count = sum(isinstance(event, ShortcutKeyStateChanged) for event in events)

    lease.close()
    dispatcher.on_release(Key("8"))

    assert sum(isinstance(event, ShortcutKeyStateChanged) for event in events) == key_event_count
    assert isinstance(events[-2], ShortcutPressInvoked)
    assert isinstance(events[-1], ShortcutPressEnded)


def test_escape_emits_only_interruption_events() -> None:
    events = []
    timers = []

    def timer_factory(delay, callback):
        timer = Timer(delay, callback)
        timers.append(timer)
        return timer

    dispatcher = create_hotkey_dispatcher({}, events.append, timer_factory=timer_factory)
    dispatcher.on_press(Key("esc"))
    timers[0].callback()
    dispatcher.on_release(Key("esc"))

    assert events == [
        InterruptionRequested("current"),
        InterruptionRequested("all"),
    ]


def test_shutdown_is_silent_and_blocks_late_timer_callback() -> None:
    events = []
    timers = []

    def timer_factory(delay, callback):
        timer = Timer(delay, callback)
        timers.append(timer)
        return timer

    dispatcher = create_hotkey_dispatcher(
        {"english": {"hotkey": "ctrl+alt+8"}},
        events.append,
        modifier_mode="ctrl_alt",
        timer_factory=timer_factory,
    )
    dispatcher.on_press(Key("ctrl"))
    dispatcher.on_press(Key("alt"))
    dispatcher.on_press(Key("8"))
    events.clear()

    dispatcher.stop()
    timers[0].callback()
    dispatcher.on_release(Key("8"))

    assert events == []
