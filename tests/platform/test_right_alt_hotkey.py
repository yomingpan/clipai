from types import SimpleNamespace
import pytest

from ClipAI.core.commands import ShortcutPressStarted, ShortcutPressThresholdReached, ShortcutPressInvoked, ShortcutPressEnded
from ClipAI.core.models import ShortcutPressId, ShortcutPressRef
from ClipAI.platform.hotkey import create_hotkey_dispatcher, _WindowsHotkeyEventFilter


class Timer:
    def __init__(self, delay, callback):
        self.delay = delay
        self.callback = callback
        self.cancelled = False
    def start(self):
        pass
    def cancel(self):
        self.cancelled = True


def make_dispatcher(events, **kwargs):
    timers = []
    clock = [0.0]
    def factory(delay, callback):
        timer = Timer(delay, callback)
        timers.append(timer)
        return timer
    dispatcher = create_hotkey_dispatcher(
        {"inline": {"hotkey": "right_alt"}}, events.append,
        timer_factory=factory, clock=lambda: clock[0], entry_panel_enabled=True, **kwargs,
    )
    return dispatcher, timers, clock


def key(name):
    return SimpleNamespace(name=name)


def test_right_alt_threshold_only_previews_and_release_invokes_then_ends():
    events = []
    dispatcher, timers, clock = make_dispatcher(events)
    dispatcher.on_press(key("alt_gr"))
    assert events == [ShortcutPressStarted(ShortcutPressId(1), "inline")]
    clock[0] = 0.5
    timers[0].callback()
    assert events == [
        ShortcutPressStarted(ShortcutPressId(1), "inline"),
        ShortcutPressThresholdReached(ShortcutPressId(1), "inline"),
    ]
    dispatcher.on_release(key("alt_gr"))
    assert events[-2:] == [
        ShortcutPressInvoked(ShortcutPressId(1), "inline", "long"),
        ShortcutPressEnded(ShortcutPressId(1), "inline", "released"),
    ]


@pytest.mark.parametrize("other", ["a", "ctrl_l", "shift_l", "tab", "esc"])
def test_any_other_key_cancels_solo_once_without_late_intent(other):
    events = []
    dispatcher, timers, clock = make_dispatcher(events)
    dispatcher.on_press(key("alt_gr"))
    dispatcher.on_press(key(other))
    dispatcher.on_press(key(other))
    clock[0] = 1
    timers[0].callback()
    dispatcher.on_release(key("alt_gr"))
    assert [e for e in events if isinstance(e, (ShortcutPressStarted, ShortcutPressThresholdReached, ShortcutPressInvoked, ShortcutPressEnded))] == [
        ShortcutPressStarted(ShortcutPressId(1), "inline"),
        ShortcutPressEnded(ShortcutPressId(1), "inline", "cancelled"),
    ]


@pytest.mark.parametrize("held", ["a", "ctrl_l", "shift_l", "alt_l", "tab"])
def test_solo_never_starts_when_another_physical_key_is_already_held(held):
    events = []
    dispatcher, timers, clock = make_dispatcher(events)
    dispatcher.on_press(key(held))
    dispatcher.on_press(key("alt_gr"))
    for timer in timers:
        timer.callback()
    dispatcher.on_release(key("alt_gr"))
    assert not any(isinstance(e, (ShortcutPressStarted, ShortcutPressInvoked)) for e in events)


@pytest.mark.parametrize("right", [key("alt_gr"), key("alt_r"), SimpleNamespace(vk=0xA5)])
def test_right_alt_native_forms_never_open_entry_panel(right):
    events = []
    dispatcher, timers, clock = make_dispatcher(events)
    dispatcher.on_press(right)
    clock[0] = 0.5
    for timer in timers:
        timer.callback()
    assert events == [
        ShortcutPressStarted(ShortcutPressId(1), "inline"),
        ShortcutPressThresholdReached(ShortcutPressId(1), "inline"),
    ]


@pytest.mark.parametrize("chorded,expected_masks", [(False, 1), (True, 0)])
def test_native_release_masks_once_and_preserves_physical_release_time(chorded, expected_masks):
    events = []
    dispatcher, timers, clock = make_dispatcher(events)
    masks = []
    hook = _WindowsHotkeyEventFilter(dispatcher, lambda: masks.append(True))
    dispatcher.on_press(key("alt_gr"))
    if chorded:
        dispatcher.on_press(key("a"))
    clock[0] = 0.499
    for _ in range(2):
        assert hook(0x0105, SimpleNamespace(vkCode=0xA5, flags=0)) is True
    clock[0] = 1.0
    timers[0].callback()
    dispatcher.on_release(key("alt_gr"))
    assert len(masks) == expected_masks
    assert not any(isinstance(e, ShortcutPressThresholdReached) for e in events)
    invoked = [e for e in events if isinstance(e, ShortcutPressInvoked)]
    assert invoked == ([] if chorded else [ShortcutPressInvoked(ShortcutPressId(1), "inline", "short")])


def test_stop_cancels_solo_and_late_timer_without_an_invocation():
    events = []
    dispatcher, timers, clock = make_dispatcher(events)
    dispatcher.on_press(key("alt_gr"))
    dispatcher.stop()
    timers[0].callback()
    dispatcher.on_release(key("alt_gr"))
    assert events == [
        ShortcutPressStarted(ShortcutPressId(1), "inline"),
        ShortcutPressEnded(ShortcutPressId(1), "inline", "cancelled"),
    ]
    assert timers[0].cancelled


@pytest.mark.parametrize("elapsed,expected", [(0.499, "short"), (0.5, "long"), (1.0, "long")])
def test_release_uses_shared_threshold_even_if_timer_has_not_run(elapsed, expected):
    events = []
    dispatcher, timers, clock = make_dispatcher(events)
    dispatcher.on_press(key("alt_gr"))
    clock[0] = elapsed
    dispatcher.on_release(key("alt_gr"))
    assert events[-2] == ShortcutPressInvoked(ShortcutPressId(1), "inline", expected)
    assert timers[0].delay == 0.5


def test_repeat_and_lagging_async_key_state_cannot_restart_live_solo():
    events = []
    dispatcher, timers, clock = make_dispatcher(events, key_is_pressed=lambda token: False)
    dispatcher.on_press(key("alt_gr"))
    dispatcher.on_press(key("alt_gr"))
    clock[0] = 0.5
    timers[0].callback()
    timers[0].callback()
    dispatcher.on_release(key("alt_gr"))
    assert [e for e in events if isinstance(e, ShortcutPressStarted)] == [ShortcutPressStarted(ShortcutPressId(1), "inline")]
    assert len([e for e in events if isinstance(e, ShortcutPressThresholdReached)]) == 1


def test_injected_keyboard_and_mouse_do_not_cancel_solo_and_old_timer_is_inert():
    events = []
    dispatcher, timers, clock = make_dispatcher(events)
    dispatcher.on_press(key("alt_gr"), injected=True)
    assert events == []
    dispatcher.on_press(key("alt_gr"))
    dispatcher.on_press(key("a"), injected=True)
    dispatcher.on_release(key("alt_gr"), injected=True)
    masks = []
    hook = _WindowsHotkeyEventFilter(dispatcher, lambda: masks.append(True))
    assert hook(0x0201, SimpleNamespace(vkCode=0, flags=0)) is True  # mouse is not a keyboard chord
    assert hook(0x0105, SimpleNamespace(vkCode=0xA5, flags=0x10)) is False
    clock[0] = 0.6
    timers[0].callback()
    dispatcher.on_release(key("alt_gr"))
    dispatcher.on_press(key("alt_gr"))
    before = list(events)
    timers[0].callback()
    assert events == before
    assert masks == []
    assert [e.press_type for e in events if isinstance(e, ShortcutPressInvoked)] == ["long"]


def test_observation_retains_solo_press_identity_until_cancelled():
    events = []
    dispatcher, timers, clock = make_dispatcher(events)
    dispatcher.on_press(key("alt_gr"))
    lease = dispatcher.observe()
    assert lease.snapshot.active_presses == (ShortcutPressRef(ShortcutPressId(1), "inline"),)
    lease.close()
    dispatcher.on_press(key("a"))
    lease = dispatcher.observe()
    assert lease.snapshot.active_presses == ()
    lease.close()
