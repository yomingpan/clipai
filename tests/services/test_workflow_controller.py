from __future__ import annotations

from ClipAI.core.models import ActionInvocation, InputDocument, InputTarget, ResolvedAction
from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.services.workflow_controller import WorkflowController


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
