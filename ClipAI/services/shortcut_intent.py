from __future__ import annotations

from ClipAI.core.commands import AppCommand, ShortcutTriggered
from ClipAI.services.shortcut_catalog import ShortcutCatalog


class ShortcutIntentCoordinator:
    """Atomic shortcut seam; sequence composition can replace this policy later."""

    def __init__(self, shortcuts: ShortcutCatalog) -> None:
        self._shortcuts = shortcuts

    def resolve(self, trigger: ShortcutTriggered) -> AppCommand:
        return self._shortcuts.resolve(trigger.shortcut_id, trigger.press_type)

    def cancel(self) -> None:
        pass
