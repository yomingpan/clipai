from __future__ import annotations

from collections.abc import Callable
from typing import TypeAlias
import uuid

from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.commands import ActionFeedbackCompleted, GuidancePreferencesCompleted, ResetFirstUseHints, SetFirstUseHintsEnabled, SubmitActionFeedback
from ClipAI.core.ports import GuidancePreferencesPresenter, UserNotifier
from ClipAI.services.action_feedback import ActionFeedbackService
from ClipAI.services.guidance_preferences import GuidancePreferencesCoordinator, GuidancePreferencesUpdate
from ClipAI.services.workflow_controller import WorkflowController


UserPersistenceRuntimeCommand: TypeAlias = SubmitActionFeedback | ActionFeedbackCompleted | SetFirstUseHintsEnabled | ResetFirstUseHints | GuidancePreferencesCompleted


class UserPersistenceRuntimeModule:
    """Owns background persistence handoff for feedback and guidance commands."""

    def __init__(
        self,
        *,
        supervisor: TaskSupervisor,
        workflow_controller: Callable[[str], WorkflowController | None],
        enqueue: Callable[[object], None],
        action_feedback: ActionFeedbackService | None = None,
        guidance_preferences: GuidancePreferencesCoordinator | None = None,
        guidance_preferences_presenter: GuidancePreferencesPresenter | None = None,
        notifier: UserNotifier | None = None,
    ) -> None:
        self._supervisor = supervisor
        self._workflow_controller = workflow_controller
        self._enqueue = enqueue
        self._action_feedback = action_feedback
        self._guidance_preferences = guidance_preferences
        self._guidance_preferences_presenter = guidance_preferences_presenter
        self._notifier = notifier

    def handle(self, command: UserPersistenceRuntimeCommand) -> None:
        if isinstance(command, SubmitActionFeedback):
            self._submit_feedback(command)
        elif isinstance(command, ActionFeedbackCompleted):
            controller = self._workflow_controller(command.session_id)
            if controller is not None:
                controller.complete_feedback(command.step_id, command.operation_id, command.error)
        elif isinstance(command, SetFirstUseHintsEnabled):
            self._begin_guidance("set", command.operation_id or uuid.uuid4().hex, command.enabled)
        elif isinstance(command, ResetFirstUseHints):
            self._begin_guidance("reset", command.operation_id or uuid.uuid4().hex)
        elif isinstance(command, GuidancePreferencesCompleted) and self._guidance_preferences is not None:
            self._project_guidance(self._guidance_preferences.complete(command.operation_id, command.error))

    def _begin_guidance(self, kind: str, operation_id: str, enabled: bool = False) -> None:
        if self._guidance_preferences is None:
            return
        update = (
            self._guidance_preferences.begin_set_enabled(enabled, operation_id)
            if kind == "set"
            else self._guidance_preferences.begin_reset(operation_id)
        )
        self._project_guidance(update)
        if update.work is None:
            return
        guidance_preferences = self._guidance_preferences
        work = update.work

        def save() -> None:
            error = guidance_preferences.execute(work)
            self._enqueue(GuidancePreferencesCompleted(operation_id, error))

        self._supervisor.submit(
            f"guidance-preferences:{operation_id}",
            save,
            lambda error: self._enqueue(GuidancePreferencesCompleted(
                operation_id,
                "無法儲存使用引導設定，請再試一次。",
            )),
        )

    def _project_guidance(self, update: GuidancePreferencesUpdate) -> None:
        if update.ignored:
            return
        if self._guidance_preferences_presenter is not None:
            self._guidance_preferences_presenter.set_guidance_preferences(update.preferences)
        if update.error and self._notifier is not None:
            self._notifier.notify("ClipAI", update.error)

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
            lambda error: self._enqueue(ActionFeedbackCompleted(
                command.session_id,
                command.step_id,
                command.operation_id,
                "無法儲存回饋，請再試一次。",
            )),
        )
