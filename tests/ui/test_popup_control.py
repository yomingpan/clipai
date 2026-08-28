from __future__ import annotations

from ClipAI.core.models import OutputOperationResult, PasteTarget
from ClipAI.ui.popup_control import PopupControl, PopupProjectionContext


class Dialog:
    def __init__(self, events: list[object] | None = None) -> None:
        self.events = events if events is not None else []

    def apply_external_output_visibility(self, visibility: str) -> bool:
        self.events.append(("visibility", visibility))
        return True


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
