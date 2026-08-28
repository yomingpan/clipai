from __future__ import annotations

from ClipAI.core.models import OutputOperationResult
from ClipAI.ui.popup_control import PopupControl


class Dialog:
    def apply_external_output_visibility(self, visibility: str) -> bool:
        raise AssertionError(f"unexpected visibility change: {visibility}")


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
