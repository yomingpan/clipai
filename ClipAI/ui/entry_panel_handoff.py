from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ClipAI.core.models import PopupBounds


class EntryPanelHandoffSource(Protocol):
    def presents(self, panel_id: str) -> bool: ...

    def current_bounds(self) -> PopupBounds | None: ...

    def hide(self) -> None: ...

    def reveal(self) -> None: ...

    def close(self) -> None: ...


class EntryPanelHandoffTarget(Protocol):
    def show(self) -> bool: ...


@dataclass(frozen=True)
class EntryPanelPopupPreparation:
    bounds: PopupBounds | None
    create_withdrawn: bool


@dataclass(frozen=True)
class EntryPanelPopupCompletion:
    committed: bool
    popup_revealed: bool


class EntryPanelPopupHandoff:
    """Own the identity-scoped visual replacement of one Panel by one Popup."""

    def __init__(self, panel: EntryPanelHandoffSource) -> None:
        self._panel = panel
        self._panel_id: str | None = None
        self._workflow_id: str | None = None
        self._preparation: EntryPanelPopupPreparation | None = None
        self._finished = False

    def begin(self, panel_id: str, workflow_id: str) -> bool:
        if not self._panel.presents(panel_id):
            return False
        self._panel_id = panel_id
        self._workflow_id = workflow_id
        self._preparation = None
        self._finished = False
        return True

    def prepare(
        self,
        workflow_id: str,
        *,
        popup_exists: bool,
    ) -> EntryPanelPopupPreparation | None:
        if not self._matches(workflow_id):
            return None
        if self._preparation is None:
            self._preparation = EntryPanelPopupPreparation(
                bounds=None if popup_exists else self._panel.current_bounds(),
                create_withdrawn=not popup_exists,
            )
        return self._preparation

    def complete(
        self,
        workflow_id: str,
        popup: EntryPanelHandoffTarget,
    ) -> EntryPanelPopupCompletion:
        preparation = self._preparation
        if preparation is None or not self._matches(workflow_id):
            return EntryPanelPopupCompletion(False, False)
        if preparation.create_withdrawn:
            self._panel.hide()
            if not popup.show():
                self._panel.reveal()
                return EntryPanelPopupCompletion(False, False)
        self._panel.close()
        self._finished = True
        return EntryPanelPopupCompletion(True, preparation.create_withdrawn)

    def _matches(self, workflow_id: str) -> bool:
        return (
            not self._finished
            and self._panel_id is not None
            and self._workflow_id == workflow_id
            and self._panel.presents(self._panel_id)
        )
