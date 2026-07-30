from ClipAI.core.commands import ShortcutPressInvoked, SpeakSelectionOrClipboard, StartAction
from ClipAI.core.models import ShortcutDefinition, ShortcutPressId
from ClipAI.services.shortcut_catalog import ShortcutCatalog
from ClipAI.services.shortcut_intent import ShortcutIntentCoordinator


def coordinator() -> ShortcutIntentCoordinator:
    return ShortcutIntentCoordinator(ShortcutCatalog([
        ShortcutDefinition("action", "ctrl+alt+8", "start_action", "english"),
        ShortcutDefinition("speech", "ctrl+alt+q", "speak_selection_or_clipboard"),
    ]))


def test_atomic_action_trigger_preserves_press_type() -> None:
    command = coordinator().resolve(ShortcutPressInvoked(ShortcutPressId(1), "action", "long"))
    assert command == StartAction("english", "long")


def test_atomic_speech_trigger_resolves_without_platform_sequence_state() -> None:
    command = coordinator().resolve(ShortcutPressInvoked(ShortcutPressId(1), "speech", "short"))
    assert isinstance(command, SpeakSelectionOrClipboard)
