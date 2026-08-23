from __future__ import annotations

from ClipAI.core.commands import AppCommand, OpenContextualQuestion, SpeakSelectionOrClipboard, StartAction
from ClipAI.core.models import PressType, ShortcutDefinition


class ShortcutCatalog:
    def __init__(self, shortcuts: list[ShortcutDefinition]) -> None:
        self._shortcuts = {shortcut.id: shortcut for shortcut in shortcuts}
        if len(self._shortcuts) != len(shortcuts):
            raise ValueError("shortcut ids must be unique")

    def hotkey_map(self) -> dict[str, dict[str, str]]:
        return {
            shortcut.id: {"hotkey": shortcut.hotkey}
            for shortcut in self._shortcuts.values()
        }

    def resolve(self, shortcut_id: str, press_type: PressType) -> AppCommand:
        shortcut = self.definition(shortcut_id)
        if shortcut.command == "start_action":
            assert shortcut.action_id is not None
            return StartAction(shortcut.action_id, press_type)
        if shortcut.command == "speak_selection_or_clipboard":
            return SpeakSelectionOrClipboard()
        if shortcut.command == "open_contextual_question":
            return OpenContextualQuestion()
        raise ValueError("push-to-talk shortcuts are dispatched from their physical press lifecycle")

    def is_push_to_talk(self, shortcut_id: str) -> bool:
        return self.definition(shortcut_id).command == "push_to_talk"

    def definition(self, shortcut_id: str) -> ShortcutDefinition:
        try:
            return self._shortcuts[shortcut_id]
        except KeyError as exc:
            raise ValueError(f"unknown shortcut: {shortcut_id}") from exc

    def definitions(self) -> tuple[ShortcutDefinition, ...]:
        return tuple(self._shortcuts.values())
