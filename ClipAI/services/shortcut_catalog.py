from __future__ import annotations

from ClipAI.core.commands import AppCommand, SpeakSelectionOrClipboard, StartAction
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
        try:
            shortcut = self._shortcuts[shortcut_id]
        except KeyError as exc:
            raise ValueError(f"unknown shortcut: {shortcut_id}") from exc
        if shortcut.command == "start_action":
            assert shortcut.action_id is not None
            return StartAction(shortcut.action_id, press_type)
        return SpeakSelectionOrClipboard()
