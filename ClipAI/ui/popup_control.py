from __future__ import annotations

import uuid
from dataclasses import dataclass
import logging
import tkinter as tk
from typing import Callable, Protocol

from ClipAI.core.commands import ActivateWorkflow, ControlSurfaceActivated, ControlSurfaceReleased, WorkflowAttentionCompleted
from ClipAI.core.models import ControlSurfaceRef, OutputActionKind, OutputOperationResult, PasteTarget, WorkflowAttention
from ClipAI.ui._popup_control_state import (
    FocusConfirmationObserved as _FocusConfirmationObserved,
    FocusEntered as _FocusEntered,
    FocusPopup,
    ForegroundLeftApplication as _ForegroundLeftApplication,
    InsidePointerPressed as _InsidePointerPressed,
    OutsideFocusCheckRequested as _OutsideFocusCheckRequested,
    OutsideFocusObserved as _OutsideFocusObserved,
    OutsidePointerPressed as _OutsidePointerPressed,
    OwnedDialogClosed as _OwnedDialogClosed,
    OwnedDialogOpened as _OwnedDialogOpened,
    PopupRegistered as _PopupRegistered,
    PopupShown as _PopupShown,
    _PopupControlState,
    PulseOutputAction,
    ReportControlSurfaceReleased,
    RequestPopupClose,
    ScheduleFocusConfirmationCheck,
    ScheduleOutsideFocusCheck,
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


@dataclass(frozen=True)
class PopupControlRegistered:
    pass


@dataclass(frozen=True)
class PopupControlShown:
    pass


@dataclass(frozen=True)
class ToolkitFocusEntered:
    pass


@dataclass(frozen=True)
class PopupInsidePointerPressed:
    pass


@dataclass(frozen=True)
class PopupOutsideFocusRequested:
    pass


@dataclass(frozen=True)
class PopupOutsidePointerPressed:
    pass


@dataclass(frozen=True)
class PopupForegroundPolled:
    pass


@dataclass(frozen=True)
class PopupOwnedDialogOpened:
    pass


@dataclass(frozen=True)
class PopupOwnedDialogClosed:
    restored: bool


class _PopupDialog(Protocol):
    lifecycle: _PopupLifecycle
    root: object
    pinned: bool

    def native_owns_foreground(self) -> bool: ...

    def is_alive(self) -> bool: ...

    def apply_external_output_visibility(self, visibility: str) -> bool | None: ...

    def flash(self, mode: str = "default") -> None: ...


class _PopupLifecycle(Protocol):
    def focus(self) -> bool: ...

    def schedule(self, delay_ms: int, callback: Callable[[], None]) -> object: ...


class _PopupSurface(Protocol):
    overflow_expanded: bool

    def set_standard_action_enabled(self, slot_id: str, enabled: bool) -> None: ...

    def pulse_standard_action(self, slot_id: str, duration_ms: int = 1000) -> None: ...

    def pulse_standard_action_error(self, slot_id: str, duration_ms: int = 1000) -> None: ...

    def show_action_message(self, text: str, duration_ms: int = 1000) -> None: ...

    def collapse_overflow(self) -> None: ...

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
        diagnostics: bool = False,
    ) -> None:
        self._workflow_id = workflow_id
        self._dialog = dialog
        self._surface = surface
        self._command_sink = command_sink
        self._request_close = request_close
        self._identity_factory = identity_factory
        self._projection_context = projection_context or PopupProjectionContext(None, None)
        self._diagnostics = diagnostics
        self._transitions = _PopupControlState()
        self._disposed = False

    @property
    def focused_inside(self) -> bool:
        return self._transitions.focused_inside

    @property
    def owns_focus(self) -> bool:
        return self._transitions.owns_focus

    def update_projection_context(self, context: PopupProjectionContext) -> None:
        if self._disposed:
            return
        self._projection_context = context
        self._surface.set_paste_focus_state(
            self.focused_inside,
            context.paste_target,
            voice_draft_editing=context.voice_draft_editing,
        )

    def observe_focus(
        self,
        event: (
            PopupControlRegistered
            | PopupControlShown
            | ToolkitFocusEntered
            | PopupInsidePointerPressed
            | PopupOutsideFocusRequested
            | PopupOutsidePointerPressed
            | PopupForegroundPolled
            | PopupOwnedDialogOpened
            | PopupOwnedDialogClosed
        ),
    ) -> None:
        if self._disposed:
            return
        if isinstance(event, PopupControlRegistered):
            self._apply_focus(_PopupRegistered())
            return
        if isinstance(event, PopupControlShown):
            self._apply_focus(_PopupShown())
            return
        if isinstance(event, ToolkitFocusEntered):
            native_foreground, toolkit_focused = self._focus_evidence()
            self._apply_focus(_FocusEntered(
                native_foreground=native_foreground,
                toolkit_focused=toolkit_focused,
            ))
            return
        if isinstance(event, PopupInsidePointerPressed):
            self._apply_focus(_InsidePointerPressed())
            self._command_sink(ActivateWorkflow(self._workflow_id))
            return
        if isinstance(event, PopupOutsideFocusRequested):
            self._apply_focus(_OutsideFocusCheckRequested())
            return
        if isinstance(event, PopupOutsidePointerPressed):
            self._apply_focus(_OutsidePointerPressed(pinned=self._dialog.pinned))
            return
        if isinstance(event, PopupForegroundPolled):
            if self.focused_inside and not self._dialog.native_owns_foreground():
                self._apply_focus(_ForegroundLeftApplication(pinned=self._dialog.pinned))
            return
        if isinstance(event, PopupOwnedDialogOpened):
            self._apply_focus(_OwnedDialogOpened())
            return
        if isinstance(event, PopupOwnedDialogClosed):
            self._apply_focus(_OwnedDialogClosed(restored=event.restored))
            return
        raise TypeError(f"unsupported PopupControl focus event: {event!r}")

    def begin_output(
        self,
        kind: OutputActionKind,
        *,
        pinned: bool = False,
    ) -> str | None:
        if self._disposed:
            return None
        operation_id = self._identity_factory()
        transition = self._transitions.begin(kind, operation_id, pinned=pinned)
        if not transition.accepted:
            return None
        self._apply(transition.actions)
        return operation_id

    def settle_output(self, result: OutputOperationResult) -> None:
        if self._disposed:
            return
        self._apply(self._transitions.acknowledge(result))

    def present_attention(self, attention: WorkflowAttention) -> None:
        if self._disposed:
            return
        self._apply(self._transitions.attention(
            attention.attention_id,
            attention.message,
            duration_ms=attention.duration_ms,
            request_focus=attention.request_focus,
            warning=attention.warning,
        ))

    def dispose(self) -> None:
        self._disposed = True

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
                if self._diagnostics:
                    native_foreground, toolkit_focused = self._focus_evidence()
                    _LOGGER.info(
                        "focus transition workflow_id=%s native_foreground=%s toolkit_focused=%s projection=%s",
                        self._workflow_id,
                        native_foreground,
                        toolkit_focused,
                        action.focused,
                    )
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
            elif isinstance(action, ScheduleFocusConfirmationCheck):
                self._schedule_focus_confirmation(action)
            elif isinstance(action, ScheduleOutsideFocusCheck):
                self._schedule_outside_focus_check(action)
            elif isinstance(action, ReportControlSurfaceReleased):
                self._command_sink(ControlSurfaceReleased(
                    ControlSurfaceRef(self._workflow_id, "workflow"),
                ))
            elif isinstance(action, RequestPopupClose):
                self._surface.collapse_overflow()
                self._request_close()
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

    def _apply_focus(self, fact: object) -> None:
        was_focused = self.focused_inside
        self._apply(self._transitions.focus(fact))
        directly_confirmed = isinstance(fact, _FocusEntered) and fact.confirmed
        newly_confirmed = (
            isinstance(fact, _FocusConfirmationObserved)
            and not was_focused
            and self.focused_inside
        )
        if directly_confirmed or newly_confirmed:
            self._report_confirmed_focus()

    def _schedule_focus_confirmation(self, action: ScheduleFocusConfirmationCheck) -> None:
        def confirm() -> None:
            if self._disposed or not self._dialog.is_alive():
                return
            native_foreground, toolkit_focused = self._focus_evidence()
            if self._diagnostics:
                _LOGGER.info(
                    "focus confirmation workflow_id=%s generation=%s attempt=%s native_foreground=%s toolkit_focused=%s",
                    self._workflow_id,
                    action.generation,
                    action.attempt,
                    native_foreground,
                    toolkit_focused,
                )
            self._apply_focus(_FocusConfirmationObserved(
                action.generation,
                action.attempt,
                native_foreground,
                toolkit_focused,
            ))

        self._dialog.lifecycle.schedule(action.delay_ms, confirm)

    def _schedule_outside_focus_check(self, action: ScheduleOutsideFocusCheck) -> None:
        def observe() -> None:
            if self._disposed or not self._dialog.is_alive():
                return
            self._apply_focus(_OutsideFocusObserved(
                action.generation,
                pinned=self._dialog.pinned,
                focused_inside=self._toolkit_focused_inside(),
            ))

        self._dialog.lifecycle.schedule(action.delay_ms, observe)

    def _report_confirmed_focus(self) -> None:
        self._command_sink(ControlSurfaceActivated(
            ControlSurfaceRef(self._workflow_id, "workflow"),
        ))
        self._command_sink(ActivateWorkflow(self._workflow_id))

    def _focus_evidence(self) -> tuple[bool, bool]:
        return self._dialog.native_owns_foreground(), self._toolkit_focused_inside()

    def _toolkit_focused_inside(self) -> bool:
        try:
            focused = self._dialog.root.focus_get()  # type: ignore[attr-defined]
            toolkit_focused = (
                focused is not None
                and focused.winfo_toplevel() is self._dialog.root
            )
        except (AttributeError, tk.TclError):
            toolkit_focused = False
        return toolkit_focused
