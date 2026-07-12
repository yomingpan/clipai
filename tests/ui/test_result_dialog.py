from __future__ import annotations

from ClipAI.core.commands import ArchiveResult, CopyResult, PasteResult, TogglePin, ToggleSpeech
from ClipAI.ui.result_dialog import ResultDialogPresenter, _SessionView


class Root:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def withdraw(self) -> None:
        self.events.append("withdraw")


class Dialog:
    def __init__(self, events: list[str]) -> None:
        self.root = Root(events)


class Surface:
    def __init__(self, selected: str | None, events: list[str]) -> None:
        self.selected = selected
        self.events = events

    def selected_text(self) -> str | None:
        return self.selected

    def set_standard_action_enabled(self, slot_id: str, enabled: bool) -> None:
        self.events.append(f"{slot_id}:{enabled}")

    def pulse_standard_action(self, slot_id: str, duration_ms: int = 1000) -> None:
        self.events.append(f"{slot_id}:pulse:{duration_ms}")

    def set_speaker_active(self, active: bool) -> None:
        self.events.append(f"speaker:{active}")

    def toggle_pin(self) -> bool:
        self.events.append("pin:toggled")
        return True


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


def test_copy_and_archive_show_feedback_before_emitting_command() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._copy("s1")
    presenter._archive("s1")
    assert events == [
        "copy:pulse:1000",
        CopyResult("s1", "selected"),
        "archive:pulse:1000",
        ArchiveResult("s1"),
    ]


def test_speaker_command_waits_for_snapshot_to_change_icon() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._toggle_speech("s1")
    assert events == [ToggleSpeech("s1", "selected")]


def test_paste_disables_and_hides_before_emitting_command() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._paste("s1")
    assert events == ["paste:False", "withdraw", PasteResult("s1", "selected")]


def test_pin_updates_visual_state_before_emitting_command() -> None:
    presenter, events = presenter_with_selection(None)
    presenter._toggle_pin("s1")
    assert events == ["pin:toggled", TogglePin("s1")]


def test_active_workflow_context_projects_selection_and_displayed_step() -> None:
    presenter, _events = presenter_with_selection("selected")
    presenter._views["s1"].content = "full result"
    presenter._views["s1"].step_id = "step-1"
    context = presenter.active_workflow_context()
    assert context.workflow_id == "s1"
    assert context.step_id == "step-1"
    assert context.content == "full result"
    assert context.selected_text == "selected"
