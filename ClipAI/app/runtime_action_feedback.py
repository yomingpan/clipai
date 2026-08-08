from __future__ import annotations

from collections.abc import Callable
from typing import TypeAlias

from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.commands import ActionFeedbackCompleted, SubmitActionFeedback
from ClipAI.services.action_feedback import ActionFeedbackService
from ClipAI.services.workflow_controller import WorkflowController


ActionFeedbackRuntimeCommand: TypeAlias = SubmitActionFeedback | ActionFeedbackCompleted


class ActionFeedbackRuntimeModule:
    """Owns background persistence and Workflow settlement for Action feedback."""

    def __init__(
        self,
        *,
        supervisor: TaskSupervisor,
        workflow_controller: Callable[[str], WorkflowController | None],
        enqueue: Callable[[object], None],
        action_feedback: ActionFeedbackService | None = None,
    ) -> None:
        self._supervisor = supervisor
        self._workflow_controller = workflow_controller
        self._enqueue = enqueue
        self._action_feedback = action_feedback

    def handle(self, command: ActionFeedbackRuntimeCommand) -> None:
        if isinstance(command, SubmitActionFeedback):
            self._submit_feedback(command)
        elif isinstance(command, ActionFeedbackCompleted):
            controller = self._workflow_controller(command.session_id)
            if controller is not None:
                controller.complete_feedback(command.step_id, command.operation_id, command.error)

    def _submit_feedback(self, command: SubmitActionFeedback) -> None:
        if self._action_feedback is None:
            return
        controller = self._workflow_controller(command.session_id)
        if controller is None:
            return
        step = controller.begin_feedback(command.step_id, command.operation_id)
        if step is None:
            return
        action_feedback = self._action_feedback

        def save() -> None:
            action_feedback.record(command.session_id, step, command)
            self._enqueue(ActionFeedbackCompleted(command.session_id, command.step_id, command.operation_id))

        self._supervisor.submit(
            f"action-feedback:{command.operation_id}",
            save,
            lambda _error: self._enqueue(ActionFeedbackCompleted(
                command.session_id,
                command.step_id,
                command.operation_id,
                "無法儲存回饋，請再試一次。",
            )),
            task_class="interactive",
        )
