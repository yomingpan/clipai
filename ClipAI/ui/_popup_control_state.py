from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from ClipAI.core.models import OutputActionKind, OutputOperationResult


PopupVisibility = Literal["hidden", "visible_activate", "visible_no_activate"]
OutputActionSlot = Literal["speaker", "copy", "paste", "archive"]
_FOCUS_CONFIRMATION_MAX_ATTEMPTS = 4


@dataclass(frozen=True)
class SetPopupVisibility:
    visibility: PopupVisibility


@dataclass(frozen=True)
class SetFocusProjection:
    focused: bool


@dataclass(frozen=True)
class FocusPopup:
    attention_id: str | None = None


@dataclass(frozen=True)
class ScheduleOutsideFocusCheck:
    generation: int
    delay_ms: int = 100


@dataclass(frozen=True)
class ScheduleFocusConfirmationCheck:
    generation: int
    attempt: int = 1
    delay_ms: int = 25


@dataclass(frozen=True)
class ReportControlSurfaceReleased:
    pass


@dataclass(frozen=True)
class RequestPopupClose:
    pass


@dataclass(frozen=True)
class SetOutputActionEnabled:
    slot_id: OutputActionSlot
    enabled: bool


@dataclass(frozen=True)
class PulseOutputAction:
    slot_id: OutputActionSlot
    error: bool = False


@dataclass(frozen=True)
class ShowOutputMessage:
    message: str
    duration_ms: int
    only_when_overflow_collapsed: bool = False
    warning: bool = False


PopupTransitionAction: TypeAlias = (
    SetPopupVisibility
    | SetFocusProjection
    | FocusPopup
    | ScheduleFocusConfirmationCheck
    | ScheduleOutsideFocusCheck
    | ReportControlSurfaceReleased
    | RequestPopupClose
    | SetOutputActionEnabled
    | PulseOutputAction
    | ShowOutputMessage
)


@dataclass(frozen=True)
class PopupRegistered:
    pass


@dataclass(frozen=True)
class PopupShown:
    pass


@dataclass(frozen=True)
class FocusEntered:
    native_foreground: bool
    toolkit_focused: bool

    @property
    def confirmed(self) -> bool:
        return self.native_foreground and self.toolkit_focused


@dataclass(frozen=True)
class FocusConfirmationObserved:
    generation: int
    attempt: int
    native_foreground: bool
    toolkit_focused: bool

    @property
    def confirmed(self) -> bool:
        return self.native_foreground and self.toolkit_focused


@dataclass(frozen=True)
class ForegroundLeftApplication:
    pinned: bool


@dataclass(frozen=True)
class OutsideFocusCheckRequested:
    pass


@dataclass(frozen=True)
class OutsideFocusObserved:
    generation: int
    pinned: bool
    focused_inside: bool


@dataclass(frozen=True)
class OutsidePointerPressed:
    pinned: bool


@dataclass(frozen=True)
class InsidePointerPressed:
    pass


@dataclass(frozen=True)
class OwnedDialogOpened:
    pass


@dataclass(frozen=True)
class OwnedDialogClosed:
    restored: bool


PopupFocusFact: TypeAlias = (
    PopupRegistered
    | PopupShown
    | FocusEntered
    | FocusConfirmationObserved
    | ForegroundLeftApplication
    | OutsideFocusCheckRequested
    | OutsideFocusObserved
    | OutsidePointerPressed
    | InsidePointerPressed
    | OwnedDialogOpened
    | OwnedDialogClosed
)


@dataclass(frozen=True)
class BeginTransition:
    accepted: bool
    actions: tuple[PopupTransitionAction, ...] = ()


@dataclass(frozen=True)
class _DeferredAttention:
    attention_id: str
    message: str
    duration_ms: int
    request_focus: bool
    warning: bool


class _PopupControlState:
    """Own popup output identities, visibility policy, and focus generations."""

    def __init__(self) -> None:
        self._operations: dict[OutputActionKind, str] = {}
        self._paste_pinned = False
        self._registered = False
        self._shown = False
        self._withdrawn_for_paste = False
        self._deferred_attention: _DeferredAttention | None = None
        self._initial_focus_established = False
        self._outside_check_pending = False
        self._focused_inside = False
        self._focus_generation = 0
        self._focus_confirmation_pending = False
        self._focus_confirmation_attempt = 0
        self._owned_dialog_active = False

    @property
    def focused_inside(self) -> bool:
        return self._focused_inside

    @property
    def owns_focus(self) -> bool:
        return (
            self._focused_inside
            or self._outside_check_pending
            or self._focus_confirmation_pending
        )

    def begin(
        self,
        kind: OutputActionKind,
        operation_id: str,
        *,
        pinned: bool = False,
    ) -> BeginTransition:
        if kind == "paste" and "paste" in self._operations:
            return BeginTransition(False)
        self._operations[kind] = operation_id
        if kind != "paste":
            return BeginTransition(True)
        self._paste_pinned = pinned
        self._withdrawn_for_paste = True
        self._mark_unfocused()
        return BeginTransition(True, (
            SetFocusProjection(False),
            SetPopupVisibility("hidden"),
        ))

    def acknowledge(
        self,
        result: OutputOperationResult,
    ) -> tuple[PopupTransitionAction, ...]:
        current_operation_id = self._operations.get(result.kind)
        if result.state == "pending":
            if current_operation_id != result.operation_id:
                return ()
            if result.kind in {"copy", "paste", "archive"}:
                return (SetOutputActionEnabled(_slot_id(result.kind), False),)
            return ()
        if current_operation_id != result.operation_id:
            return ()

        self._operations.pop(result.kind, None)
        actions: list[PopupTransitionAction] = []
        slot_id = _slot_id(result.kind)
        if result.kind in {"copy", "paste", "archive"}:
            actions.append(SetOutputActionEnabled(slot_id, True))
        if result.kind == "paste":
            actions.extend(self._finish_paste(result))
        actions.extend(_feedback_actions(result, slot_id))
        if result.kind == "paste":
            actions.extend(self._release_deferred_attention())
        return tuple(actions)

    def focus(self, fact: PopupFocusFact) -> tuple[PopupTransitionAction, ...]:
        if isinstance(fact, PopupRegistered):
            self._registered = True
            return ()
        if isinstance(fact, PopupShown):
            self._shown = True
            self._withdrawn_for_paste = False
            return ()
        if isinstance(fact, FocusEntered):
            if not fact.confirmed:
                if self._focused_inside:
                    return ()
                self._mark_unfocused()
                actions: list[PopupTransitionAction] = [SetFocusProjection(False)]
                if fact.toolkit_focused and self._visible and not self._owned_dialog_active and "paste" not in self._operations:
                    actions.append(self._begin_focus_confirmation())
                return tuple(actions)
            if "paste" not in self._operations:
                self._withdrawn_for_paste = False
            self._mark_focused()
            return (SetFocusProjection(True),)
        if isinstance(fact, FocusConfirmationObserved):
            if (
                not self._focus_confirmation_pending
                or fact.generation != self._focus_generation
                or fact.attempt != self._focus_confirmation_attempt
            ):
                return ()
            if not fact.confirmed:
                if (
                    not fact.toolkit_focused
                    or fact.attempt >= _FOCUS_CONFIRMATION_MAX_ATTEMPTS
                    or self._owned_dialog_active
                    or "paste" in self._operations
                ):
                    self._focus_confirmation_pending = False
                    return ()
                self._focus_confirmation_attempt += 1
                return (ScheduleFocusConfirmationCheck(
                    self._focus_generation,
                    self._focus_confirmation_attempt,
                ),)
            if "paste" not in self._operations:
                self._withdrawn_for_paste = False
            self._mark_focused()
            return (SetFocusProjection(True),)
        if isinstance(fact, ForegroundLeftApplication):
            if not self._focused_inside or self._owned_dialog_active or "paste" in self._operations:
                return ()
            self._mark_unfocused()
            actions: list[PopupTransitionAction] = [
                SetFocusProjection(False),
                ReportControlSurfaceReleased(),
            ]
            if not fact.pinned:
                actions.append(RequestPopupClose())
            return tuple(actions)
        if isinstance(fact, OutsideFocusCheckRequested):
            if (
                not self._ready
                or self._outside_check_pending
                or self._owned_dialog_active
                or "paste" in self._operations
            ):
                return ()
            self._outside_check_pending = True
            self._focus_generation += 1
            return (ScheduleOutsideFocusCheck(self._focus_generation),)
        if isinstance(fact, OutsideFocusObserved):
            if fact.generation != self._focus_generation or not self._outside_check_pending:
                return ()
            self._outside_check_pending = False
            self._focused_inside = fact.focused_inside
            actions: list[PopupTransitionAction] = [SetFocusProjection(fact.focused_inside)]
            if not fact.focused_inside:
                actions.append(ReportControlSurfaceReleased())
                if self._ready and not fact.pinned:
                    actions.append(RequestPopupClose())
            return tuple(actions)
        if isinstance(fact, OutsidePointerPressed):
            if (
                not self._visible
                or self._owned_dialog_active
                or "paste" in self._operations
            ):
                return ()
            self._mark_unfocused()
            actions = [SetFocusProjection(False), ReportControlSurfaceReleased()]
            if not fact.pinned:
                actions.append(RequestPopupClose())
            return tuple(actions)
        if isinstance(fact, InsidePointerPressed):
            if (
                self._focused_inside
                or not self._visible
                or self._owned_dialog_active
                or "paste" in self._operations
            ):
                return ()
            self._mark_unfocused()
            return (FocusPopup(), self._begin_focus_confirmation())
        if isinstance(fact, OwnedDialogOpened):
            self._owned_dialog_active = True
            self._mark_unfocused()
            return (SetFocusProjection(False),)
        if isinstance(fact, OwnedDialogClosed):
            self._owned_dialog_active = False
            if fact.restored:
                self._mark_focused()
                return (FocusPopup(), SetFocusProjection(True))
            self._mark_unfocused()
            return (SetFocusProjection(False),)
        raise TypeError(f"unsupported popup focus fact: {fact!r}")

    def attention(
        self,
        attention_id: str,
        message: str,
        *,
        duration_ms: int,
        request_focus: bool,
        warning: bool,
    ) -> tuple[PopupTransitionAction, ...]:
        """Present a runtime-owned attention request through the focus owner."""
        attention = _DeferredAttention(
            attention_id,
            message,
            duration_ms,
            request_focus,
            warning,
        )
        if "paste" in self._operations:
            self._deferred_attention = attention
            return ()
        return self._attention_actions(attention)

    def _attention_actions(
        self,
        attention: _DeferredAttention,
    ) -> tuple[PopupTransitionAction, ...]:
        actions: list[PopupTransitionAction] = []
        if self._withdrawn_for_paste:
            visibility: PopupVisibility = (
                "visible_activate" if attention.request_focus else "visible_no_activate"
            )
            actions.append(SetPopupVisibility(visibility))
        if attention.request_focus:
            actions.append(FocusPopup(attention.attention_id))
        actions.append(ShowOutputMessage(
            attention.message,
            attention.duration_ms,
            warning=attention.warning,
        ))
        return tuple(actions)

    def _release_deferred_attention(self) -> tuple[PopupTransitionAction, ...]:
        attention, self._deferred_attention = self._deferred_attention, None
        return self._attention_actions(attention) if attention is not None else ()

    @property
    def _ready(self) -> bool:
        return self._visible and self._initial_focus_established

    @property
    def _visible(self) -> bool:
        return self._registered and self._shown

    def _mark_focused(self) -> None:
        self._initial_focus_established = True
        self._focused_inside = True
        self._outside_check_pending = False
        self._focus_confirmation_pending = False
        self._focus_generation += 1

    def _mark_unfocused(self) -> None:
        self._focused_inside = False
        self._outside_check_pending = False
        self._focus_confirmation_pending = False
        self._focus_generation += 1

    def _begin_focus_confirmation(self) -> ScheduleFocusConfirmationCheck:
        self._focus_confirmation_pending = True
        self._focus_confirmation_attempt = 1
        return ScheduleFocusConfirmationCheck(
            self._focus_generation,
            self._focus_confirmation_attempt,
        )

    def _finish_paste(
        self,
        result: OutputOperationResult,
    ) -> tuple[PopupTransitionAction, ...]:
        pinned, self._paste_pinned = self._paste_pinned, False
        if result.state == "failed":
            self._withdrawn_for_paste = False
            return (SetPopupVisibility("visible_activate"),)
        if result.state in {"cancelled", "cleanup_failed"}:
            self._withdrawn_for_paste = False
            return (SetPopupVisibility("visible_no_activate"),)
        if result.state == "dispatched_unconfirmed" and pinned:
            self._withdrawn_for_paste = False
            return (SetPopupVisibility("visible_no_activate"),)
        return ()


def _slot_id(kind: OutputActionKind) -> OutputActionSlot:
    return "speaker" if kind == "speech" else kind


def _feedback_actions(
    result: OutputOperationResult,
    slot_id: OutputActionSlot,
) -> tuple[PopupTransitionAction, ...]:
    if result.state == "succeeded":
        actions: list[PopupTransitionAction] = [PulseOutputAction(slot_id)]
        if result.kind == "archive":
            actions.append(ShowOutputMessage(
                "已封存",
                1000,
                only_when_overflow_collapsed=True,
            ))
        return tuple(actions)
    if result.state == "dispatched_unconfirmed":
        actions = [PulseOutputAction(slot_id)]
        if result.message:
            actions.append(ShowOutputMessage(result.message, 2500))
        return tuple(actions)
    if result.state == "cleanup_failed":
        actions = [PulseOutputAction(slot_id, error=True)]
        if result.message:
            actions.append(ShowOutputMessage(result.message, 3000))
        return tuple(actions)
    if result.state == "cancelled" and result.kind == "paste":
        return (ShowOutputMessage(result.message or "已取消貼上", 1500),)
    if result.state == "failed":
        actions = [PulseOutputAction(slot_id, error=True)]
        if result.error is not None:
            actions.append(ShowOutputMessage(result.error.message, 1500))
        return tuple(actions)
    return ()
