from ClipAI.core.commands import ShortcutTriggered, StartAction
from ClipAI.core.models import ShortcutDefinition
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


def test_long_composer_release_then_action_routes_to_speech():
    events = []
    coordinator, _ = make_sequence(events)
    assert coordinator.resolve(ShortcutTriggered("speech", "long")) is None
    assert coordinator.resolve(ShortcutTriggered("speech", "long_release")) is None
    assert coordinator.resolve(ShortcutTriggered("action", "short")) == StartAction("english", "short", "speech")
    assert events == ["cancel-active", "waiting"]


def test_timeout_reports_error_and_cancel_is_quiet():
    events = []
    coordinator, timers = make_sequence(events)
    coordinator.resolve(ShortcutTriggered("speech", "long"))
    coordinator.resolve(ShortcutTriggered("speech", "long_release"))
    timers[-1].callback()
    assert events[-1] == "Shortcut sequence timed out."
    coordinator.resolve(ShortcutTriggered("", "cancel"))
    assert events.count("Shortcut sequence timed out.") == 1


def test_invalid_second_key_reports_immediately():
    events = []
    coordinator, timers = make_sequence(events)
    coordinator.resolve(ShortcutTriggered("speech", "long"))
    coordinator.resolve(ShortcutTriggered("speech", "long_release"))
    coordinator.resolve(ShortcutTriggered("", "invalid"))
    assert events[-1] == "Invalid shortcut sequence."
    assert timers[-1].cancelled is True
