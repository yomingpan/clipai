from __future__ import annotations

import uuid
from typing import Callable, Protocol

from ClipAI.core.models import OutputActionKind, OutputOperationResult
from ClipAI.ui.popup_external_output import (
    PopupExternalOutputTransitions,
    PulseOutputAction,
    SetOutputActionEnabled,
    ShowOutputMessage,
)


class _PopupDialog(Protocol):
    def apply_external_output_visibility(self, visibility: str) -> bool | None: ...


class _PopupSurface(Protocol):
    overflow_expanded: bool

    def set_standard_action_enabled(self, slot_id: str, enabled: bool) -> None: ...

    def pulse_standard_action(self, slot_id: str, duration_ms: int = 1000) -> None: ...

    def pulse_standard_action_error(self, slot_id: str, duration_ms: int = 1000) -> None: ...

    def show_action_message(self, text: str, duration_ms: int = 1000) -> None: ...


def _new_operation_id() -> str:
    return uuid.uuid4().hex


class PopupControl:
    """Own Popup control state and project its observable UI lifecycle."""

    def __init__(
        self,
        workflow_id: str,
        dialog: _PopupDialog,
        surface: _PopupSurface,
        *,
        command_sink: Callable[[object], None],
        request_close: Callable[[], None],
        identity_factory: Callable[[], str] = _new_operation_id,
    ) -> None:
        self._workflow_id = workflow_id
        self._dialog = dialog
        self._surface = surface
        self._command_sink = command_sink
        self._request_close = request_close
        self._identity_factory = identity_factory
        self._transitions = PopupExternalOutputTransitions()

    def begin_output(
        self,
        kind: OutputActionKind,
        *,
        pinned: bool = False,
    ) -> str | None:
        operation_id = self._identity_factory()
        transition = self._transitions.begin(kind, operation_id, pinned=pinned)
        if not transition.accepted:
            return None
        self._apply(transition.actions)
        return operation_id

    def settle_output(self, result: OutputOperationResult) -> None:
        self._apply(self._transitions.acknowledge(result))

    def _apply(self, actions: tuple[object, ...]) -> None:
        for action in actions:
            if isinstance(action, SetOutputActionEnabled):
                self._surface.set_standard_action_enabled(action.slot_id, action.enabled)
            elif isinstance(action, PulseOutputAction):
                if action.error:
                    self._surface.pulse_standard_action_error(action.slot_id)
                else:
                    self._surface.pulse_standard_action(action.slot_id)
            elif isinstance(action, ShowOutputMessage):
                if action.only_when_overflow_collapsed and self._surface.overflow_expanded:
                    continue
                self._surface.show_action_message(action.message, action.duration_ms)
            else:
                raise TypeError(f"unsupported PopupControl action: {action!r}")
