from __future__ import annotations

import uuid
from dataclasses import dataclass
import logging
from typing import Callable, Protocol

from ClipAI.core.commands import WorkflowAttentionCompleted
from ClipAI.core.models import OutputActionKind, OutputOperationResult, PasteTarget, WorkflowAttention
from ClipAI.ui.popup_external_output import (
    FocusPopup,
    PopupExternalOutputTransitions,
    PulseOutputAction,
    SetFocusProjection,
    SetOutputActionEnabled,
    SetPopupVisibility,
    ShowOutputMessage,
)


_LOGGER = logging.getLogger("clipai.ui.popup_control")


@dataclass(frozen=True)
class PopupProjectionContext:
    paste_target: PasteTarget | None
    voice_draft_editing: bool | None


class _PopupDialog(Protocol):
    lifecycle: _PopupLifecycle

    def apply_external_output_visibility(self, visibility: str) -> bool | None: ...

    def flash(self, mode: str = "default") -> None: ...


class _PopupLifecycle(Protocol):
    def focus(self) -> bool: ...


class _PopupSurface(Protocol):
    overflow_expanded: bool

    def set_standard_action_enabled(self, slot_id: str, enabled: bool) -> None: ...

    def pulse_standard_action(self, slot_id: str, duration_ms: int = 1000) -> None: ...

    def pulse_standard_action_error(self, slot_id: str, duration_ms: int = 1000) -> None: ...

    def show_action_message(self, text: str, duration_ms: int = 1000) -> None: ...

    def set_paste_focus_state(
        self,
        focused: bool,
        target: PasteTarget | None,
        *,
        voice_draft_editing: bool | None,
    ) -> None: ...


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
        projection_context: PopupProjectionContext | None = None,
        _transition_state: PopupExternalOutputTransitions | None = None,
    ) -> None:
        self._workflow_id = workflow_id
        self._dialog = dialog
        self._surface = surface
        self._command_sink = command_sink
        self._request_close = request_close
        self._identity_factory = identity_factory
        self._projection_context = projection_context or PopupProjectionContext(None, None)
        self._transitions = _transition_state or PopupExternalOutputTransitions()

    @property
    def focused_inside(self) -> bool:
        return self._transitions.focused_inside

    @property
    def owns_focus(self) -> bool:
        return self._transitions.owns_focus

    def update_projection_context(self, context: PopupProjectionContext) -> None:
        self._projection_context = context
        self._surface.set_paste_focus_state(
            self.focused_inside,
            context.paste_target,
            voice_draft_editing=context.voice_draft_editing,
        )

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

    def present_attention(self, attention: WorkflowAttention) -> None:
        self._apply(self._transitions.attention(
            attention.attention_id,
            attention.message,
            duration_ms=attention.duration_ms,
            request_focus=attention.request_focus,
            warning=attention.warning,
        ))

    def _apply(self, actions: tuple[object, ...]) -> None:
        for action in actions:
            if isinstance(action, SetPopupVisibility):
                applied = self._dialog.apply_external_output_visibility(action.visibility)
                if applied is False:
                    _LOGGER.warning(
                        "popup visibility application failed workflow_id=%s visibility=%s",
                        self._workflow_id,
                        action.visibility,
                    )
            elif isinstance(action, SetFocusProjection):
                self._surface.set_paste_focus_state(
                    action.focused,
                    self._projection_context.paste_target,
                    voice_draft_editing=self._projection_context.voice_draft_editing,
                )
            elif isinstance(action, FocusPopup):
                focus_acquired = self._dialog.lifecycle.focus()
                if action.attention_id is not None:
                    self._command_sink(WorkflowAttentionCompleted(
                        action.attention_id,
                        self._workflow_id,
                        focus_acquired,
                    ))
            elif isinstance(action, SetOutputActionEnabled):
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
                if action.warning:
                    self._dialog.flash("warning")
            else:
                raise TypeError(f"unsupported PopupControl action: {action!r}")
