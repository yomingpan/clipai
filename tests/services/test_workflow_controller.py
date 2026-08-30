from __future__ import annotations

import pytest

from ClipAI.core.models import ActionFeedbackContract, ActionInvocation, ActionLanguagePackIdentity, ActionLanguageProvenance, FeedbackReason, InputDocument, InputTarget, ResolvedAction
from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.services.workflow_controller import CONTEXTUAL_SOURCE_MAX_CHARS, WorkflowController


class Presenter:
    def __init__(self) -> None:
        self.snapshots = []

    def render(self, snapshot) -> None:
        self.snapshots.append(snapshot)


def action(action_id: str = "a") -> ResolvedAction:
    return ResolvedAction(action_id, action_id, "system", "{input}", "short", "selection_or_clipboard", "popup", 0.2)


def invocation(invocation_id: str, parent: str | None = None) -> ActionInvocation:
    document = InputDocument(f"input-{invocation_id}", "workflow_result", "w1", parent)
    return ActionInvocation(invocation_id, "a", "short", InputTarget("workflow_result", document), workflow_id="w1", parent_step_id=parent)


def controller() -> WorkflowController:
    return WorkflowController(SessionSnapshot("w1", 0, SessionStatus.CREATED, "a", "A", "model"), Presenter())


def test_completion_emits_precise_accepted_step_identity_once() -> None:
    accepted = []
    workflow = WorkflowController(
        SessionSnapshot("w1", 0, SessionStatus.CREATED, "a", "A", "model"),
        Presenter(),
        on_step_accepted=lambda workflow_id, step_id: accepted.append((workflow_id, step_id)),
    )
    current = invocation("accepted")
    stale = invocation("stale")
    resolved = action()
    workflow.begin_invocation(current, resolved)

    workflow.complete(
        current,
        resolved,
        current.input_target.document,
        "result",
        ("copy",),
    )
    workflow.complete(
        stale,
        resolved,
        stale.input_target.document,
        "late result",
        ("copy",),
    )

    assert accepted == [("w1", "accepted")]


def test_contextual_source_capture_enters_question_state_with_fixed_snapshot() -> None:
    workflow = controller()
    token = workflow.begin_contextual_source_capture("capture-1")

    snapshot = workflow.complete_contextual_source_capture(
        "capture-1",
        InputDocument("fixed source", "selection"),
    )

    assert token.is_cancelled is False
    assert snapshot is not None
    assert snapshot.status is SessionStatus.CONTEXT_QUESTION
    assert snapshot.contextual_source_text == "fixed source"
    assert snapshot.contextual_source_kind == "selection"
    assert snapshot.source_preview == "Selection: fixed source"
    assert snapshot.question_composer_revision == 1


def test_contextual_source_capture_rejects_stale_and_oversized_results() -> None:
    workflow = controller()
    workflow.begin_contextual_source_capture("capture-1")
    workflow.begin_contextual_source_capture("capture-2")

    assert workflow.complete_contextual_source_capture(
        "capture-1", InputDocument("stale", "selection")
    ) is None
    with pytest.raises(ValueError, match="太長"):
        workflow.complete_contextual_source_capture(
            "capture-2",
            InputDocument("x" * (CONTEXTUAL_SOURCE_MAX_CHARS + 1), "clipboard"),
        )


def test_question_composer_request_is_rejected_during_provider_activity() -> None:
    workflow = controller()
    workflow.begin_contextual_source_capture("capture-1")
    workflow.complete_contextual_source_capture(
        "capture-1",
        InputDocument("fixed source", "selection"),
    )
    active = ActionInvocation(
        "provider-1",
        "contextual_question",
        "short",
        InputTarget("workflow_result", InputDocument("question", "selection")),
        workflow_id="w1",
    )
    workflow.begin_invocation(active, action("contextual_question"))

    assert workflow.request_question_composer() is None


def complete_step(workflow: WorkflowController, invocation_id: str, parent: str | None = None, result: str | None = None) -> None:
    inv = invocation(invocation_id, parent)
    resolved = action()
    workflow.begin_invocation(inv, resolved)
    workflow.complete(inv, resolved, inv.input_target.document, result or f"result-{invocation_id}", ("copy",))


def test_history_back_does_not_execute_work_and_preserves_steps() -> None:
    workflow = controller()
    complete_step(workflow, "one")
    complete_step(workflow, "two", "one")
    revision = workflow.snapshot.revision
    workflow.navigate_back()
    assert workflow.snapshot.content == "result-one"
    assert len(workflow.snapshot.steps) == 2
    assert workflow.snapshot.revision == revision + 1


def test_new_success_from_historical_step_truncates_forward_history() -> None:
    workflow = controller()
    complete_step(workflow, "one")
    complete_step(workflow, "two", "one")
    workflow.navigate_back()
    complete_step(workflow, "branch", "one")
    assert [step.step_id for step in workflow.snapshot.steps] == ["one", "branch"]


def test_failure_keeps_last_successful_content_and_history() -> None:
    workflow = controller()
    complete_step(workflow, "one")
    inv = invocation("fail", "one")
    workflow.begin_invocation(inv, action())
    workflow.fail("fail", "provider failed")
    assert workflow.snapshot.content == "result-one"
    assert [step.step_id for step in workflow.snapshot.steps] == ["one"]
    assert workflow.snapshot.error == "provider failed"


def test_late_completion_from_replaced_invocation_is_ignored() -> None:
    workflow = controller()
    old = invocation("old")
    new = invocation("new")
    resolved = action()
    workflow.begin_invocation(old, resolved)
    workflow.begin_invocation(new, resolved)
    assert workflow.complete(old, resolved, old.input_target.document, "late", ()) is None
    workflow.complete(new, resolved, new.input_target.document, "current", ())
    assert workflow.snapshot.content == "current"


def test_provider_delta_is_identity_scoped_and_marks_partial_content() -> None:
    workflow = controller()
    old = invocation("old")
    current = invocation("current")
    resolved = action()
    workflow.begin_invocation(old, resolved)
    workflow.begin_invocation(current, resolved)

    assert workflow.append_provider_text("old", "late") is None
    snapshot = workflow.append_provider_text("current", "partial")

    assert snapshot is not None
    assert snapshot.content == "partial"
    assert snapshot.result_completeness == "partial"
    assert snapshot.available_actions == ("copy",)


def test_partial_provider_failure_preserves_copyable_text_without_step() -> None:
    workflow = controller()
    current = invocation("current")
    workflow.begin_invocation(current, action())
    workflow.append_provider_text("current", "useful partial")

    workflow.fail("current", "provider disconnected")

    assert workflow.snapshot.content == "useful partial"
    assert workflow.snapshot.result_completeness == "partial"
    assert workflow.snapshot.available_actions == ("copy",)
    assert workflow.snapshot.steps == ()


def test_feedback_lifecycle_is_owned_by_completed_step_and_ignores_late_completion() -> None:
    workflow = controller()
    contract = ActionFeedbackContract("Shorten", "Do not change meaning", (FeedbackReason("meaning_lost", "Meaning lost"),))
    provenance = ActionLanguageProvenance(
        ActionLanguagePackIdentity("zh-TW", "1.0.0", "zh-TW"),
        "sha256:contract",
        "sha256:resources",
    )
    resolved = ResolvedAction(
        "a", "A", "system", "{input}", "short", "selection_or_clipboard", "popup", 0.2,
        feedback_contract=contract, version_id="version-1", action_language=provenance,
    )
    document = InputDocument("input", "selection")
    first = ActionInvocation("one", "a", "short", InputTarget("external_text", document), workflow_id="w1")
    workflow.begin_invocation(first, resolved)
    workflow.complete(first, resolved, document, "result", ("copy",), provider="openai", model="gpt-test")

    step = workflow.begin_feedback("one", "feedback-1")
    assert step is not None
    assert step.provider == "openai"
    assert step.model == "gpt-test"
    assert step.action_language == provenance
    assert workflow.snapshot.feedback_state == "pending"
    assert workflow.complete_feedback("one", "stale") is None
    workflow.complete_feedback("one", "feedback-1")

    assert workflow.snapshot.feedback_state == "succeeded"
    assert workflow.begin_feedback("one", "feedback-2") is None


def test_feedback_remains_available_when_input_is_a_previous_workflow_result() -> None:
    workflow = controller()
    contract = ActionFeedbackContract("Shorten", "Do not change meaning", (FeedbackReason("meaning_lost", "Meaning lost"),))
    resolved = ResolvedAction(
        "a", "A", "system", "{input}", "short", "selection_or_clipboard", "popup", 0.2,
        feedback_contract=contract, version_id="version-1",
    )
    inv = invocation("one")
    workflow.begin_invocation(inv, resolved)
    workflow.complete(inv, resolved, inv.input_target.document, "result", ("copy",))

    assert workflow.begin_feedback("one", "feedback-1") is not None


def test_completion_projects_one_time_guidance_without_reappearing_in_history() -> None:
    workflow = controller()
    inv = invocation("one")
    resolved = action()
    workflow.begin_invocation(inv, resolved)
    workflow.complete(inv, resolved, inv.input_target.document, "result", (), show_guidance_hint=True)
    assert workflow.snapshot.show_guidance_hint is True

    complete_step(workflow, "two", "one")
    workflow.navigate_back()
    assert workflow.snapshot.show_guidance_hint is False


def test_feedback_completion_offscreen_is_remembered_without_overwriting_current_step() -> None:
    workflow = controller()
    contract = ActionFeedbackContract("Shorten", "Do not change meaning", (FeedbackReason("meaning_lost", "Meaning lost"),))
    resolved = ResolvedAction(
        "a", "A", "system", "{input}", "short", "selection_or_clipboard", "popup", 0.2,
        feedback_contract=contract, version_id="version-1",
    )
    document = InputDocument("input", "selection")
    first = ActionInvocation("one", "a", "short", InputTarget("external_text", document), workflow_id="w1")
    workflow.begin_invocation(first, resolved)
    workflow.complete(first, resolved, document, "first", ("copy",))
    assert workflow.begin_feedback("one", "feedback-1") is not None
    second = ActionInvocation("two", "a", "short", InputTarget("external_text", document), workflow_id="w1", parent_step_id="one")
    workflow.begin_invocation(second, resolved)
    workflow.complete(second, resolved, document, "second", ("copy",))

    assert workflow.complete_feedback("one", "feedback-1") is None
    assert workflow.snapshot.content == "second"
    workflow.navigate_back()
    assert workflow.snapshot.feedback_state == "succeeded"
