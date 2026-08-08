from __future__ import annotations

from collections.abc import Callable
from typing import TypeAlias
import uuid

from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.commands import (
    ActionFeedbackCompleted,
    GuidancePreferencesCompleted,
    ResetFirstUseHints,
    SetFirstUseHintsEnabled,
    SetSpeechSpeed,
    SpeechSpeedPreferencesCompleted,
    SubmitActionFeedback,
)
from ClipAI.core.models import SpeechSpeed
from ClipAI.core.ports import GuidancePreferencesPresenter, OperationTracker, SpeechSpeedPresenter, UserNotifier
from ClipAI.services.action_feedback import ActionFeedbackService
from ClipAI.services.user_preferences import UserPreferencesCoordinator, UserPreferencesUpdate
from ClipAI.services.workflow_controller import WorkflowController


UserPersistenceRuntimeCommand: TypeAlias = (
    SubmitActionFeedback
    | ActionFeedbackCompleted
    | SetFirstUseHintsEnabled
    | ResetFirstUseHints
    | GuidancePreferencesCompleted
    | SetSpeechSpeed
    | SpeechSpeedPreferencesCompleted
)


class UserPersistenceRuntimeModule:
    """Owns background persistence handoff for feedback and user preferences."""

    def __init__(
        self,
        *,
        supervisor: TaskSupervisor,
        workflow_controller: Callable[[str], WorkflowController | None],
        enqueue: Callable[[object], None],
        action_feedback: ActionFeedbackService | None = None,
        user_preferences: UserPreferencesCoordinator | None = None,
        guidance_preferences_presenter: GuidancePreferencesPresenter | None = None,
        speech_speed_presenter: SpeechSpeedPresenter | None = None,
        operation_tracker: OperationTracker | None = None,
        notifier: UserNotifier | None = None,
    ) -> None:
        self._supervisor = supervisor
        self._workflow_controller = workflow_controller
        self._enqueue = enqueue
        self._action_feedback = action_feedback
        self._user_preferences = user_preferences
        self._guidance_preferences_presenter = guidance_preferences_presenter
        self._speech_speed_presenter = speech_speed_presenter
        self._operation_tracker = operation_tracker
        self._notifier = notifier

    def handle(self, command: UserPersistenceRuntimeCommand) -> None:
        if isinstance(command, SubmitActionFeedback):
            self._submit_feedback(command)
        elif isinstance(command, ActionFeedbackCompleted):
            controller = self._workflow_controller(command.session_id)
            if controller is not None:
                controller.complete_feedback(command.step_id, command.operation_id, command.error)
        elif isinstance(command, SetFirstUseHintsEnabled):
            self._begin_preference("guidance_enabled", command.operation_id or uuid.uuid4().hex, enabled=command.enabled)
        elif isinstance(command, ResetFirstUseHints):
            self._begin_preference("guidance_reset", command.operation_id or uuid.uuid4().hex)
        elif isinstance(command, SetSpeechSpeed):
            self._begin_preference("speech_speed", command.operation_id or uuid.uuid4().hex, speed=command.speed)
        elif isinstance(command, (GuidancePreferencesCompleted, SpeechSpeedPreferencesCompleted)):
            if self._user_preferences is not None:
                self._project_preferences(self._user_preferences.complete(command.operation_id, command.error))

    def _begin_preference(
        self,
        kind: str,
        operation_id: str,
        *,
        enabled: bool = False,
        speed: SpeechSpeed | None = None,
    ) -> None:
        if self._user_preferences is None:
            return
        if kind == "guidance_enabled":
            update = self._user_preferences.begin_set_guidance_enabled(enabled, operation_id)
        elif kind == "guidance_reset":
            update = self._user_preferences.begin_reset_guidance(operation_id)
        elif speed is not None:
            update = self._user_preferences.begin_set_speech_speed(speed, operation_id)
        else:
            return
        self._project_preferences(update)
        if update.work is None:
            return
        user_preferences = self._user_preferences
        work = update.work
        completion = SpeechSpeedPreferencesCompleted if kind == "speech_speed" else GuidancePreferencesCompleted
        unexpected_error = (
            "Could not save speech speed. The previous speed remains active."
            if kind == "speech_speed"
            else "無法儲存使用引導設定，請再試一次。"
        )

        def save() -> None:
            error = user_preferences.execute(work)
            self._enqueue(completion(operation_id, error))

        self._supervisor.submit(
            f"{'speech-speed-preferences' if kind == 'speech_speed' else 'guidance-preferences'}:{operation_id}",
            save,
            lambda _error: self._enqueue(completion(
                operation_id,
                unexpected_error,
            )),
            task_class="interactive",
        )

    def _project_preferences(self, update: UserPreferencesUpdate) -> None:
        if update.ignored:
            return
        if self._guidance_preferences_presenter is not None:
            self._guidance_preferences_presenter.set_guidance_preferences(update.guidance)
        if self._speech_speed_presenter is not None:
            self._speech_speed_presenter.set_speech_speed(update.speech_speed)
        if update.error and self._notifier is not None:
            self._notifier.notify("ClipAI", update.error)
        if update.error and self._operation_tracker is not None:
            self._operation_tracker.report_error(update.error)

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
