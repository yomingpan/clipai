from ClipAI.core.commands import ShortcutPressInvoked, StartAction
from ClipAI.core.models import ShortcutDefinition, ShortcutPressId
from ClipAI.services.shortcut_catalog import ShortcutCatalog
from ClipAI.services.shortcut_sequence import ShortcutSequenceCoordinator


class Timer:
    def __init__(self, _delay, callback):
        self.callback = callback
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


def make_sequence(events):
    timers = []
    catalog = ShortcutCatalog([
        ShortcutDefinition("action", "ctrl+alt+8", "start_action", "english"),
        ShortcutDefinition("speech", "ctrl+alt+q", "speak_selection_or_clipboard"),
    ])
    coordinator = ShortcutSequenceCoordinator(
        catalog,
        schedule=lambda delay, callback: timers.append(Timer(delay, callback)) or timers[-1],
        on_waiting=lambda: events.append("waiting"),
        on_error=lambda message, _suggestion: events.append(message),
        on_cancel_active=lambda: events.append("cancel-active"),
    )
    return coordinator, timers


def invoke(shortcut_id: str, press_type: str, press_id: int = 1) -> ShortcutPressInvoked:
    return ShortcutPressInvoked(ShortcutPressId(press_id), shortcut_id, press_type)


def test_held_long_composer_then_action_routes_to_speech_before_release():
    events = []
    coordinator, _ = make_sequence(events)
    assert coordinator.resolve(invoke("speech", "long")) is None
    assert coordinator.resolve(invoke("action", "short", 2)) == StartAction("english", "short", "speech")
    assert events == ["cancel-active", "waiting"]


def test_timeout_reports_error_and_cancel_is_quiet():
    events = []
    coordinator, timers = make_sequence(events)
    coordinator.resolve(invoke("speech", "long"))
    timers[-1].callback()
    assert events[-1] == "Shortcut sequence timed out."
    coordinator.cancel()
    assert events.count("Shortcut sequence timed out.") == 1


def test_invalid_second_key_reports_immediately():
    events = []
    coordinator, timers = make_sequence(events)
    coordinator.resolve(invoke("speech", "long"))
    coordinator.reject_attempt()
    assert events[-1] == "Invalid shortcut sequence."
    assert timers[-1].cancelled is True
