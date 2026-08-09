from __future__ import annotations

from ClipAI.core.models import PasteTarget
from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.core.voice import VoiceOrigin
from ClipAI.services.workflow_controller import WorkflowController
from ClipAI.core.models import ActionInvocation, InputDocument, InputTarget, ResolvedAction


class Presenter:
    def __init__(self) -> None:
        self.snapshots = []

    def render(self, snapshot) -> None:
        self.snapshots.append(snapshot)


def controller(text: str = "hello", presenter: Presenter | None = None) -> WorkflowController:
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
        presenter or Presenter(),
    )


def test_workflow_controller_applies_voice_transition_and_renders_once() -> None:
    presenter = Presenter()
    workflow = controller("hello world", presenter)
    target = workflow.freeze_voice_insertion(6, 11)
    assert target is not None

    snapshot = workflow.apply_voice_finalization(target, "ClipAI")

    assert snapshot is not None
    assert snapshot.content == "hello ClipAI"
    assert len(presenter.snapshots) == 2
    assert presenter.snapshots[-1] == snapshot


def test_workflow_controller_does_not_render_rejected_voice_transition() -> None:
    presenter = Presenter()
    workflow = controller(presenter=presenter)
    target = workflow.freeze_voice_insertion(5, 5)
    assert target is not None
    workflow.edit_voice_draft(0, "edited")
    render_count = len(presenter.snapshots)

    assert workflow.apply_voice_finalization(target, " late") is None
    assert workflow.snapshot.content == "edited"
    assert len(presenter.snapshots) == render_count


def test_first_action_from_voice_origin_can_navigate_back_to_review() -> None:
    presenter = Presenter()
    workflow = controller("hello", presenter)
    action = ResolvedAction("rewrite", "Rewrite", "system", "{input}", "short", "selection_or_clipboard", "popup", None)
    invocation = ActionInvocation("invoke-1", "rewrite", "short", InputTarget("workflow_result", InputDocument("hello", "workflow_result", "voice-workflow", "voice-origin")), workflow_id="voice-workflow", parent_step_id="voice-origin")
    workflow.begin_invocation(invocation, action)

    completed = workflow.complete(invocation, action, invocation.input_target.document, "rewritten", ("copy",))

    assert completed is not None and completed.can_navigate_back is True
    assert workflow.navigate_back() is not None
    assert workflow.snapshot.status is SessionStatus.VOICE_REVIEW
    assert presenter.snapshots[-1] == workflow.snapshot
    assert len(presenter.snapshots) == 4
