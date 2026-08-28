from __future__ import annotations

from ClipAI.core.commands import ActivateWorkflow, ControlSurfaceActivated, ControlSurfaceReleased, WorkflowAttentionCompleted
from ClipAI.core.models import ControlSurfaceRef
from ClipAI.core.models import OutputOperationResult, PasteTarget, WorkflowAttention
from ClipAI.ui.popup_control import (
    PopupControl,
    PopupForegroundPolled,
    PopupInsidePointerPressed,
    PopupOutsideFocusRequested,
    PopupOutsidePointerPressed,
    PopupOwnedDialogClosed,
    PopupOwnedDialogOpened,
    PopupControlRegistered,
    PopupControlShown,
    PopupProjectionContext,
    ToolkitFocusEntered,
)


class Dialog:
    def __init__(self, events: list[object] | None = None) -> None:
        self.events = events if events is not None else []
        self.lifecycle = Lifecycle(self.events)
        self.root = Root(self)
        self.native_foreground = True
        self.toolkit_focused = True
        self.pinned = False
        self.alive = True

    def apply_external_output_visibility(self, visibility: str) -> bool:
        self.events.append(("visibility", visibility))
        return True

    def flash(self, mode: str = "default") -> None:
        self.events.append(("flash", mode))

    def native_owns_foreground(self) -> bool:
        return self.native_foreground

    def is_alive(self) -> bool:
        return self.alive


class Root:
    def __init__(self, dialog: Dialog) -> None:
        self.dialog = dialog

    def focus_get(self):
        return self if self.dialog.toolkit_focused else None

    def winfo_toplevel(self):
        return self


class Lifecycle:
    def __init__(self, events: list[object]) -> None:
        self.events = events
        self.callbacks: list[tuple[int, object]] = []

    def focus(self) -> bool:
        self.events.append(("focus-request",))
        return True

    def schedule(self, delay_ms: int, callback) -> str:
        self.callbacks.append((delay_ms, callback))
        return f"scheduled-{len(self.callbacks)}"


class Surface:
    def __init__(self) -> None:
        self.events: list[object] = []

    def set_standard_action_enabled(self, slot_id: str, enabled: bool) -> None:
        self.events.append(("enabled", slot_id, enabled))

    def pulse_standard_action(self, slot_id: str, duration_ms: int = 1000) -> None:
        self.events.append(("pulse", slot_id, duration_ms))

    def pulse_standard_action_error(self, slot_id: str, duration_ms: int = 1000) -> None:
        self.events.append(("error", slot_id, duration_ms))

    def show_action_message(self, text: str, duration_ms: int = 1000) -> None:
        self.events.append(("message", text, duration_ms))

    def set_paste_focus_state(
        self,
        focused: bool,
        target: PasteTarget | None,
        *,
        voice_draft_editing: bool,
    ) -> None:
        self.events.append(("focus", focused, target, voice_draft_editing))

    def collapse_overflow(self) -> None:
        self.events.append(("collapse-overflow",))


def test_output_lifecycle_is_observed_through_popup_control_interface() -> None:
    surface = Surface()
    control = PopupControl(
        "w1",
        Dialog(),
        surface,
        command_sink=lambda _command: None,
        request_close=lambda: None,
        identity_factory=lambda: "copy-1",
    )

    operation_id = control.begin_output("copy")
    control.settle_output(OutputOperationResult("stale", "w1", "copy", "succeeded"))
    control.settle_output(OutputOperationResult(operation_id, "w1", "copy", "pending"))
    control.settle_output(OutputOperationResult(operation_id, "w1", "copy", "succeeded"))

    assert operation_id == "copy-1"
    assert surface.events == [
        ("enabled", "copy", False),
        ("enabled", "copy", True),
        ("pulse", "copy", 1000),
    ]


def test_paste_admission_and_visibility_are_owned_by_popup_control() -> None:
    events: list[object] = []
    dialog = Dialog(events)
    surface = Surface()
    surface.events = events
    target = PasteTarget("hwnd:10", 42, "Notepad", "Draft", 1)
    control = PopupControl(
        "w1",
        dialog,
        surface,
        command_sink=lambda _command: None,
        request_close=lambda: None,
        identity_factory=lambda: "paste-1",
        projection_context=PopupProjectionContext(target, voice_draft_editing=False),
    )

    operation_id = control.begin_output("paste", pinned=True)
    overlapping = control.begin_output("paste", pinned=True)
    control.settle_output(OutputOperationResult(operation_id, "w1", "paste", "pending"))
    control.settle_output(OutputOperationResult(
        operation_id,
        "w1",
        "paste",
        "dispatched_unconfirmed",
        message="Paste status",
    ))

    assert operation_id == "paste-1"
    assert overlapping is None
    assert events == [
        ("focus", False, target, False),
        ("visibility", "hidden"),
        ("enabled", "paste", False),
        ("enabled", "paste", True),
        ("visibility", "visible_no_activate"),
        ("pulse", "paste", 1000),
        ("message", "Paste status", 2500),
    ]


def test_attention_actuation_is_observed_through_popup_control_interface() -> None:
    events: list[object] = []
    dialog = Dialog(events)
    surface = Surface()
    surface.events = events
    control = PopupControl(
        "w1",
        dialog,
        surface,
        command_sink=events.append,
        request_close=lambda: None,
    )

    control.present_attention(WorkflowAttention(
        "attention-1",
        "w1",
        "Voice Input is unavailable",
        duration_ms=1500,
        request_focus=True,
        warning=True,
    ))

    assert events == [
        ("focus-request",),
        WorkflowAttentionCompleted("attention-1", "w1", True),
        ("message", "Voice Input is unavailable", 1500),
        ("flash", "warning"),
    ]


def test_delayed_native_focus_is_confirmed_inside_popup_control() -> None:
    events: list[object] = []
    dialog = Dialog(events)
    dialog.native_foreground = False
    surface = Surface()
    surface.events = events
    control = PopupControl(
        "w1",
        dialog,
        surface,
        command_sink=events.append,
        request_close=lambda: None,
    )

    control.observe_focus(PopupControlRegistered())
    control.observe_focus(PopupControlShown())
    control.observe_focus(ToolkitFocusEntered())
    dialog.native_foreground = True
    _delay_ms, confirmation = dialog.lifecycle.callbacks[-1]
    confirmation()

    assert [delay for delay, _callback in dialog.lifecycle.callbacks] == [25]
    assert ("focus", False, None, None) in events
    assert ("focus", True, None, None) in events
    assert events.count(ControlSurfaceActivated(ControlSurfaceRef("w1", "workflow"))) == 1
    assert events.count(ActivateWorkflow("w1")) == 1


def test_inside_pointer_requests_native_focus_before_confirmation() -> None:
    events: list[object] = []
    dialog = Dialog(events)
    dialog.native_foreground = False
    surface = Surface()
    surface.events = events
    control = PopupControl(
        "w1",
        dialog,
        surface,
        command_sink=events.append,
        request_close=lambda: events.append(("close",)),
    )
    control.observe_focus(PopupControlRegistered())
    control.observe_focus(PopupControlShown())

    control.observe_focus(PopupInsidePointerPressed())

    assert ("focus-request",) in events
    assert events.count(ActivateWorkflow("w1")) == 1
    assert not any(isinstance(event, ControlSurfaceActivated) for event in events)
    assert [delay for delay, _callback in dialog.lifecycle.callbacks] == [25]


def test_outside_focus_observation_releases_and_closes_unpinned_popup() -> None:
    events: list[object] = []
    dialog = Dialog(events)
    surface = Surface()
    surface.events = events
    control = PopupControl(
        "w1",
        dialog,
        surface,
        command_sink=events.append,
        request_close=lambda: events.append(("close",)),
    )
    control.observe_focus(PopupControlRegistered())
    control.observe_focus(PopupControlShown())
    control.observe_focus(ToolkitFocusEntered())
    events.clear()

    control.observe_focus(PopupOutsideFocusRequested())
    dialog.toolkit_focused = False
    delay_ms, observe = dialog.lifecycle.callbacks[-1]
    observe()

    assert delay_ms == 100
    assert events == [
        ("focus", False, None, None),
        ControlSurfaceReleased(ControlSurfaceRef("w1", "workflow")),
        ("collapse-overflow",),
        ("close",),
    ]


def test_outside_pointer_closes_even_before_initial_focus_is_confirmed() -> None:
    events: list[object] = []
    dialog = Dialog(events)
    surface = Surface()
    surface.events = events
    control = PopupControl(
        "w1",
        dialog,
        surface,
        command_sink=events.append,
        request_close=lambda: events.append(("close",)),
    )
    control.observe_focus(PopupControlRegistered())
    control.observe_focus(PopupControlShown())

    control.observe_focus(PopupOutsidePointerPressed())

    assert events == [
        ("focus", False, None, None),
        ControlSurfaceReleased(ControlSurfaceRef("w1", "workflow")),
        ("collapse-overflow",),
        ("close",),
    ]


def test_foreground_poll_and_owned_dialog_handoff_use_popup_control_guards() -> None:
    events: list[object] = []
    dialog = Dialog(events)
    surface = Surface()
    surface.events = events
    control = PopupControl(
        "w1",
        dialog,
        surface,
        command_sink=events.append,
        request_close=lambda: events.append(("close",)),
    )
    control.observe_focus(PopupControlRegistered())
    control.observe_focus(PopupControlShown())
    control.observe_focus(ToolkitFocusEntered())
    events.clear()

    control.observe_focus(PopupOwnedDialogOpened())
    dialog.native_foreground = False
    control.observe_focus(PopupForegroundPolled())
    control.observe_focus(PopupOwnedDialogClosed(restored=True))

    assert events == [
        ("focus", False, None, None),
        ("focus-request",),
        ("focus", True, None, None),
    ]


def test_dispose_suppresses_late_scheduled_focus_side_effects() -> None:
    events: list[object] = []
    dialog = Dialog(events)
    dialog.native_foreground = False
    surface = Surface()
    surface.events = events
    control = PopupControl(
        "w1",
        dialog,
        surface,
        command_sink=events.append,
        request_close=lambda: events.append(("close",)),
    )
    control.observe_focus(PopupControlRegistered())
    control.observe_focus(PopupControlShown())
    control.observe_focus(ToolkitFocusEntered())
    _delay_ms, confirmation = dialog.lifecycle.callbacks[-1]
    events.clear()

    control.dispose()
    dialog.native_foreground = True
    confirmation()
    control.observe_focus(PopupOutsidePointerPressed())
    control.present_attention(WorkflowAttention("late", "w1", "late"))

    assert events == []


def test_focus_confirmation_retries_are_bounded_to_four_observations() -> None:
    dialog = Dialog()
    dialog.native_foreground = False
    control = PopupControl(
        "w1",
        dialog,
        Surface(),
        command_sink=lambda _command: None,
        request_close=lambda: None,
    )
    control.observe_focus(PopupControlRegistered())
    control.observe_focus(PopupControlShown())

    control.observe_focus(ToolkitFocusEntered())
    for index in range(4):
        _delay_ms, confirmation = dialog.lifecycle.callbacks[index]
        confirmation()

    assert [delay for delay, _callback in dialog.lifecycle.callbacks] == [25, 25, 25, 25]
    assert control.focused_inside is False


def test_new_confirmed_focus_invalidates_stale_outside_observation() -> None:
    events: list[object] = []
    dialog = Dialog(events)
    surface = Surface()
    control = PopupControl(
        "w1",
        dialog,
        surface,
        command_sink=events.append,
        request_close=lambda: events.append(("close",)),
    )
    control.observe_focus(PopupControlRegistered())
    control.observe_focus(PopupControlShown())
    control.observe_focus(ToolkitFocusEntered())
    control.observe_focus(PopupOutsideFocusRequested())
    _delay_ms, stale_observation = dialog.lifecycle.callbacks[-1]

    control.observe_focus(ToolkitFocusEntered())
    dialog.toolkit_focused = False
    stale_observation()

    assert control.focused_inside is True
    assert not any(isinstance(event, ControlSurfaceReleased) for event in events)
    assert ("close",) not in events
