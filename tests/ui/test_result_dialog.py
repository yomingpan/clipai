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

    def pulse_standard_action(self, slot_id: str, duration_ms: int = 800) -> None:
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
        "copy:pulse:800",
        CopyResult("s1", "selected"),
        "archive:pulse:800",
        ArchiveResult("s1"),
    ]


def test_speaker_icon_changes_before_emitting_command() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._toggle_speech("s1")
    assert events == ["speaker:True", ToggleSpeech("s1", "selected")]


def test_paste_disables_and_hides_before_emitting_command() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._paste("s1")
    assert events == ["paste:False", "withdraw", PasteResult("s1", "selected")]


def test_pin_updates_visual_state_before_emitting_command() -> None:
    presenter, events = presenter_with_selection(None)
    presenter._toggle_pin("s1")
    assert events == ["pin:toggled", TogglePin("s1")]
