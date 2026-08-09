from __future__ import annotations

from ClipAI.core.models import PasteTarget
from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.core.voice import VoiceOrigin
from ClipAI.services.workflow_controller import WorkflowController


class Presenter:
    def render(self, snapshot) -> None:
        self.snapshot = snapshot


def controller(text: str = "hello") -> WorkflowController:
    origin = VoiceOrigin(PasteTarget("hwnd:1", 1, "Editor", "private", 1), text)
    return WorkflowController(
        SessionSnapshot(
            "voice-workflow",
            0,
            SessionStatus.VOICE_REVIEW,
            "voice_input",
            "Voice Input",
            "",
            content=text,
            available_actions=("copy", "paste", "follow_up"),
            result_completeness="complete",
            voice_origin=origin,
        ),
        Presenter(),
    )


def test_voice_capture_freezes_selection_and_applies_at_that_range() -> None:
    workflow = controller("hello world")
    target = workflow.freeze_voice_insertion(6, 11)

    assert target is not None
    snapshot = workflow.apply_voice_finalization(target, "ClipAI")

    assert snapshot is not None
    assert snapshot.content == "hello ClipAI"
    assert snapshot.voice_origin is not None
    assert snapshot.voice_origin.revision == 1


def test_stale_capture_cannot_overwrite_a_newer_voice_edit() -> None:
    workflow = controller()
    target = workflow.freeze_voice_insertion(5, 5)
    assert target is not None

    workflow.edit_voice_draft(0, "edited")

    assert workflow.apply_voice_finalization(target, " late") is None
    assert workflow.snapshot.content == "edited"


def test_invalid_voice_edit_revision_is_ignored() -> None:
    workflow = controller()

    assert workflow.edit_voice_draft(3, "wrong") is None
    assert workflow.snapshot.content == "hello"
