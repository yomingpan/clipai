from __future__ import annotations

from typing import TypeAlias

from ClipAI.core.commands import CloseShortcutGuide, OpenShortcutGuide, SelectShortcutGuideItem, ShortcutInputEvent
from ClipAI.core.models import ShortcutObservationSnapshot
from ClipAI.core.ports import ShortcutGuidePresenter
from ClipAI.services.shortcut_guide import ShortcutGuideCatalog, ShortcutGuideCoordinator


ShortcutGuideRuntimeCommand: TypeAlias = (
    OpenShortcutGuide
    | CloseShortcutGuide
    | SelectShortcutGuideItem
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

    def handle(
        self,
        command: ShortcutGuideRuntimeCommand,
        observation: ShortcutObservationSnapshot = ShortcutObservationSnapshot(),
    ) -> None:
        if isinstance(command, OpenShortcutGuide):
            snapshot = self._coordinator.open(
                command.guide_id,
                self._catalog.items(),
                observation,
            )
            self._presenter.show_shortcut_guide(snapshot)
        elif isinstance(command, CloseShortcutGuide):
            if self._coordinator.close(command.guide_id):
                self._presenter.close_shortcut_guide()
        elif isinstance(command, SelectShortcutGuideItem):
            selected_snapshot = self._coordinator.select(command.shortcut_id)
            if selected_snapshot is not None:
                self._presenter.set_shortcut_guide(selected_snapshot)

    def consume(self, event: ShortcutInputEvent) -> bool:
        decision = self._coordinator.handle(event)
        if not decision.consumed:
            return False
        if decision.snapshot is not None:
            self._presenter.set_shortcut_guide(decision.snapshot)
        return True
