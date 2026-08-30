from __future__ import annotations

from dataclasses import dataclass, replace

from ClipAI.core.errors import ActionLanguagePackErrorCode
from ClipAI.core.models import ActionLanguagePackSelectionState


@dataclass(frozen=True)
class ActionLanguageSelectionWork:
    operation_id: str
    pack_id: str


@dataclass(frozen=True)
class ActionLanguageSelectionUpdate:
    state: ActionLanguagePackSelectionState
    work: ActionLanguageSelectionWork | None = None
    ignored: bool = False


class ActionLanguageSelectionCoordinator:
    """Owns restart-only selection intent and settlement identity."""

    def __init__(self, state: ActionLanguagePackSelectionState) -> None:
        self._state = state

    @property
    def state(self) -> ActionLanguagePackSelectionState:
        return self._state

    def begin(self, pack_id: str, operation_id: str) -> ActionLanguageSelectionUpdate:
        if self._state.pending_pack_id is not None:
            return ActionLanguageSelectionUpdate(self._state, ignored=True)
        available = {
            descriptor.identity.pack_id for descriptor in self._state.available_packs
        }
        if pack_id not in available:
            self._state = replace(
                self._state,
                message="The selected Action Language is unavailable.",
            )
            return ActionLanguageSelectionUpdate(self._state)
        if pack_id == self._state.selected_pack_id and self._state.recovery is None:
            return ActionLanguageSelectionUpdate(self._state, ignored=True)
        self._state = replace(
            self._state,
            pending_pack_id=pack_id,
            operation_id=operation_id,
            message="Validating Action Language...",
        )
        return ActionLanguageSelectionUpdate(
            self._state,
            ActionLanguageSelectionWork(operation_id, pack_id),
        )

    def complete(
        self,
        operation_id: str,
        pack_id: str,
        error: ActionLanguagePackErrorCode | None = None,
    ) -> ActionLanguageSelectionUpdate:
        if (
            self._state.operation_id != operation_id
            or self._state.pending_pack_id != pack_id
        ):
            return ActionLanguageSelectionUpdate(self._state, ignored=True)
        if error is not None:
            self._state = replace(
                self._state,
                pending_pack_id=None,
                operation_id="",
                message=_failure_message(error),
            )
            return ActionLanguageSelectionUpdate(self._state)
        self._state = replace(
            self._state,
            selected_pack_id=pack_id,
            pending_pack_id=None,
            operation_id="",
            restart_required=pack_id != self._state.active_pack.pack_id,
            recovery=None,
            message=(
                "Action Language saved. Restart ClipAI to apply it."
                if pack_id != self._state.active_pack.pack_id
                else "Action Language selection saved."
            ),
        )
        return ActionLanguageSelectionUpdate(self._state)


def _failure_message(error: ActionLanguagePackErrorCode) -> str:
    if error == "selection_save_failed":
        return "Could not save Action Language. The previous selection remains."
    return "Could not validate Action Language. The previous selection remains."
