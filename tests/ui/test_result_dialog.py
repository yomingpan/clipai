from __future__ import annotations

from ClipAI.core.commands import ArchiveResult, CopyResult, PasteResult, SubmitActionFeedback, TogglePin, ToggleSpeech
from ClipAI.core.models import ActionFeedbackContract, FeedbackReason, OutputOperationResult
from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.ui.result_dialog import PopupFocusLifecycle, ResultDialogPresenter, _SessionView, _content_render_key


class Root:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def withdraw(self) -> None:
        self.events.append("withdraw")


class Dialog:
    def __init__(self, events: list[str], *, alive: bool = True) -> None:
        self.root = Root(events)
        self.alive = alive

    def is_alive(self) -> bool:
        return self.alive

    def close(self) -> None:
        self.alive = False
        self.root.events.append("close")


class Surface:
    def __init__(self, selected: str | None, events: list[str]) -> None:
        self.selected = selected
        self.events = events
        self.overflow_expanded = False
        self.feedback_available = False

    def selected_text(self) -> str | None:
        return self.selected

    def set_standard_action_enabled(self, slot_id: str, enabled: bool) -> None:
        self.events.append(f"{slot_id}:{enabled}")

    def pulse_standard_action(self, slot_id: str, duration_ms: int = 1000) -> None:
        self.events.append(f"{slot_id}:pulse:{duration_ms}")

    def pulse_standard_action_error(self, slot_id: str, duration_ms: int = 1000) -> None:
        self.events.append(f"{slot_id}:error:{duration_ms}")

    def show_action_message(self, text: str, duration_ms: int = 1000) -> None:
        self.events.append(f"message:{text}:{duration_ms}")

    def set_speaker_active(self, active: bool) -> None:
        self.events.append(f"speaker:{active}")

    def toggle_pin(self) -> bool:
        self.events.append("pin:toggled")
        return True

    def configure_action_contract(self, contract, input_source: str) -> None:
        self.events.append(("contract", contract, input_source))

    def configure_feedback(self, contract, state, message, on_submit) -> None:
        self.feedback_submit = on_submit
        self.events.append(("feedback", state, message))

    def hide_feedback(self) -> None:
        self.events.append("feedback:hidden")

    def toggle_feedback_overlay(self) -> bool:
        self.events.append("feedback:toggled")
        return self.feedback_available

    def close_feedback_overlay(self) -> None:
        self.events.append("feedback:closed")


def presenter_with_selection(selected: str | None):
    events: list[str] = []
    presenter = ResultDialogPresenter.__new__(ResultDialogPresenter)
    presenter._views = {"s1": _SessionView(Dialog(events), Surface(selected, events))}
    presenter._command_sink = lambda command: events.append(command)
    presenter._active_workflow_id = "s1"
    return presenter, events


def test_text_command_carries_popup_selection() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._send_text_command("s1", CopyResult)
    assert events == [CopyResult("s1", "selected")]


def test_copy_and_archive_wait_for_typed_acknowledgment() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._copy("s1")
    presenter._archive("s1")
    assert len(events) == 2
    assert isinstance(events[0], CopyResult) and events[0].text == "selected" and events[0].operation_id
    assert isinstance(events[1], ArchiveResult) and events[1].text == "selected" and events[1].operation_id


def test_acknowledgment_projects_success_and_ignores_stale_operation() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._views["s1"].output_operations["archive"] = "new"
    presenter._apply_output_operation(OutputOperationResult("old", "s1", "archive", "succeeded"))
    assert events == []
    presenter._apply_output_operation(OutputOperationResult("new", "s1", "archive", "succeeded"))
    assert "archive:pulse:1000" in events


def test_late_output_operation_evicts_dead_view_without_touching_surface() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._views["s1"].dialog.alive = False

    presenter._apply_output_operation(OutputOperationResult("late", "s1", "archive", "pending"))

    assert events == []
    assert presenter._views == {}
    assert presenter._active_workflow_id is None


def test_late_completed_snapshot_evicts_dead_view_without_touching_surface() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._views["s1"].dialog.alive = False
    snapshot = SessionSnapshot("s1", 1, SessionStatus.COMPLETED, "a", "A", "model", content="late")

    presenter._apply(snapshot)

    assert events == []
    assert presenter._views == {}
    assert presenter._active_workflow_id is None


def test_closed_snapshot_cleanup_is_idempotent() -> None:
    presenter, events = presenter_with_selection("selected")
    snapshot = SessionSnapshot("s1", 1, SessionStatus.CLOSED, "a", "A", "model")

    presenter._apply(snapshot)
    presenter._apply(snapshot)

    assert events == ["close"]
    assert presenter._views == {}
    assert presenter._active_workflow_id is None


def test_speaker_command_waits_for_snapshot_to_change_icon() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._toggle_speech("s1")
    assert len(events) == 1
    assert isinstance(events[0], ToggleSpeech) and events[0].text == "selected" and events[0].operation_id


def test_speech_operation_projects_to_speaker_slot() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._apply_output_operation(OutputOperationResult("speech-op", "s1", "speech", "pending"))
    presenter._apply_output_operation(OutputOperationResult("speech-op", "s1", "speech", "succeeded"))
    assert "speaker:pulse:1000" in events


def test_speech_failure_projects_to_speaker_slot() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._apply_output_operation(OutputOperationResult("speech-op", "s1", "speech", "pending"))
    presenter._apply_output_operation(OutputOperationResult("speech-op", "s1", "speech", "failed"))
    assert "speaker:error:1000" in events


def test_paste_emits_identified_command_and_waits_for_pending_projection() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._paste("s1")
    assert len(events) == 1
    assert isinstance(events[0], PasteResult) and events[0].text == "selected" and events[0].operation_id


def test_pin_updates_visual_state_before_emitting_command() -> None:
    presenter, events = presenter_with_selection(None)
    presenter._toggle_pin("s1")
    assert events == ["pin:toggled", TogglePin("s1")]


def test_feedback_submission_is_a_typed_identified_command() -> None:
    presenter, events = presenter_with_selection(None)

    presenter._submit_feedback("s1", "step-1", "needs_adjustment", "meaning_lost", "Too aggressive", True)

    assert len(events) == 1
    command = events[0]
    assert isinstance(command, SubmitActionFeedback)
    assert command.session_id == "s1"
    assert command.step_id == "step-1"
    assert command.operation_id
    assert command.reason == "meaning_lost"
    assert command.save_case is True


def test_ctrl_r_feedback_request_reports_unsupported_recipe() -> None:
    presenter, events = presenter_with_selection(None)

    presenter._toggle_feedback("s1")

    assert events == ["feedback:toggled", "message:此 Recipe 尚未啟用回饋:1000"]


def test_ctrl_r_feedback_request_opens_supported_recipe_overlay() -> None:
    presenter, events = presenter_with_selection(None)
    presenter._views["s1"].surface.feedback_available = True

    presenter._toggle_feedback("s1")

    assert events == ["feedback:toggled"]


def test_active_workflow_context_projects_selection_and_displayed_step() -> None:
    presenter, _events = presenter_with_selection("selected")
    presenter._views["s1"].content = "full result"
    presenter._views["s1"].step_id = "step-1"
    context = presenter.active_workflow_context()
    assert context.workflow_id == "s1"
    assert context.step_id == "step-1"
    assert context.content == "full result"
    assert context.selected_text == "selected"


def test_focus_lifecycle_ignores_focus_out_until_registered_shown_and_focused() -> None:
    lifecycle = PopupFocusLifecycle()
    assert lifecycle.request_outside_check() is False
    lifecycle.registered = True
    lifecycle.shown = True
    assert lifecycle.request_outside_check() is False
    lifecycle.initial_focus_established = True
    assert lifecycle.request_outside_check() is True
    assert lifecycle.request_outside_check() is False


def test_focus_lifecycle_closes_only_for_unpinned_outside_focus() -> None:
    lifecycle = PopupFocusLifecycle(True, True, True)
    assert lifecycle.request_outside_check() is True
    assert lifecycle.finish_outside_check(pinned=False, focused_inside=True) is False
    assert lifecycle.request_outside_check() is True
    assert lifecycle.finish_outside_check(pinned=True, focused_inside=False) is False
    assert lifecycle.request_outside_check() is True
    assert lifecycle.finish_outside_check(pinned=False, focused_inside=False) is True


def test_content_key_ignores_speaking_and_pin_snapshot_changes() -> None:
    snapshot = SessionSnapshot("s1", 0, SessionStatus.COMPLETED, "a", "A", "model", content="long content")
    changed_ui_state = snapshot.evolve(speaking=True, pinned=True)
    assert _content_render_key(changed_ui_state) == _content_render_key(snapshot)


def test_content_key_changes_for_new_content() -> None:
    snapshot = SessionSnapshot("s1", 0, SessionStatus.COMPLETED, "a", "A", "model", content="first")
    changed_content = snapshot.evolve(content="second")
    assert _content_render_key(changed_content) != _content_render_key(snapshot)
