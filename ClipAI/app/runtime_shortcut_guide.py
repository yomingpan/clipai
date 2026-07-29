from __future__ import annotations

from typing import TypeAlias

from ClipAI.core.commands import CloseShortcutGuide, OpenShortcutGuide, SelectShortcutGuideItem, ShortcutGestureProgressed, ShortcutTriggered
from ClipAI.core.ports import ShortcutGuidePresenter
from ClipAI.services.shortcut_guide import ShortcutGuideCatalog, ShortcutGuideCoordinator


ShortcutGuideRuntimeCommand: TypeAlias = (
    OpenShortcutGuide
    | CloseShortcutGuide
    | SelectShortcutGuideItem
    | ShortcutGestureProgressed
)


class ShortcutGuideRuntimeModule:
    def __init__(
        self,
        *,
        catalog: ShortcutGuideCatalog,
        coordinator: ShortcutGuideCoordinator,
        presenter: ShortcutGuidePresenter,
    ) -> None:
        self._catalog = catalog
        self._coordinator = coordinator
        self._presenter = presenter

    @property
    def is_open(self) -> bool:
        return self._coordinator.snapshot is not None

    def wants_progress(self, gesture_id: int) -> bool:
        return self._coordinator.wants_progress(gesture_id)

    def handle(self, command: ShortcutGuideRuntimeCommand) -> None:
        if isinstance(command, OpenShortcutGuide):
            snapshot = self._coordinator.open(command.guide_id, self._catalog.items())
            self._presenter.show_shortcut_guide(snapshot)
        elif isinstance(command, CloseShortcutGuide):
            if self._coordinator.close(command.guide_id):
                self._presenter.close_shortcut_guide()
        elif isinstance(command, SelectShortcutGuideItem):
            snapshot = self._coordinator.select(command.shortcut_id)
            if snapshot is not None:
                self._presenter.set_shortcut_guide(snapshot)
        elif isinstance(command, ShortcutGestureProgressed):
            snapshot = self._coordinator.observe(command)
            if snapshot is not None:
                self._presenter.set_shortcut_guide(snapshot)

    def consume(self, trigger: ShortcutTriggered) -> bool:
        decision = self._coordinator.consume(trigger)
        if not decision.consumed:
            return False
        if decision.close_requested:
            self._presenter.close_shortcut_guide()
        elif decision.snapshot is not None:
            self._presenter.set_shortcut_guide(decision.snapshot)
        return True
