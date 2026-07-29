from __future__ import annotations

import customtkinter as ctk

from ClipAI.app.config_loader import load_action_catalog, load_app_config, load_shortcut_catalog
from ClipAI.core.commands import CloseShortcutGuide, SelectShortcutGuideItem
from ClipAI.services.shortcut_guide import ShortcutGuideCatalog, ShortcutGuideCoordinator
from ClipAI.ui.shortcut_guide import ShortcutGuideDialog


class MockShortcutGuideSurface:
    def __init__(self) -> None:
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")
        self.root = ctk.CTk()
        self.root.withdraw()
        self.coordinator = ShortcutGuideCoordinator()
        app, *_ = load_app_config("config/config.yaml")
        actions = load_action_catalog("config/actions.yaml")
        shortcuts = load_shortcut_catalog("config/shortcuts.yaml", actions=actions)
        catalog = ShortcutGuideCatalog(shortcuts, actions, modifier_mode=app.modifier_mode)
        self.dialog = ShortcutGuideDialog(self.root, self.handle)
        self.dialog.show(self.coordinator.open("mock-guide", catalog.items()))

    def handle(self, command: object) -> None:
        if isinstance(command, SelectShortcutGuideItem):
            snapshot = self.coordinator.select(command.shortcut_id)
            if snapshot is not None:
                self.dialog.apply(snapshot)
        elif isinstance(command, CloseShortcutGuide):
            self.coordinator.close(command.guide_id)
            self.dialog.destroy()
            self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    MockShortcutGuideSurface().run()
