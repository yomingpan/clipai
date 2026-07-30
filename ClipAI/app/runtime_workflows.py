from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, TypeAlias
import uuid

from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.commands import ActivateWorkflow, AppCommand, CancelSession, CloseSession, FollowUp, NavigateWorkflowBack, ReleaseForegroundWorkflow, ShortcutTriggered, StartAction, TogglePin
from ClipAI.core.models import ActionInvocation, InputDocument, InputTarget
from ClipAI.core.ports import ApplicationView, OperationTracker, UserNotifier, WorkflowContextReader
from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.services.action_catalog import ActionCatalog
from ClipAI.services.execute_action import ActionExecutor
from ClipAI.services.input_target_resolver import InputTargetResolver
from ClipAI.services.provider_configuration import ProviderConfigurationCoordinator
from ClipAI.services.provider_binding import ProviderExecutionBinding
from ClipAI.services.shortcut_catalog import ShortcutCatalog
from ClipAI.services.shortcut_intent import ShortcutIntentCoordinator
from ClipAI.services.shortcut_sequence import ShortcutSequenceCoordinator
from ClipAI.services.speech_coordinator import SpeechCoordinator
from ClipAI.services.workflow_controller import WorkflowController
from ClipAI.support.diagnostics import IncidentReporter


WorkflowPresentation: TypeAlias = Literal["visible", "headless"]


@dataclass(frozen=True)
class WorkflowInvocationFailed:
    workflow_id: str
    error: BaseException


@dataclass(frozen=True)
class HeadlessWorkflowFinished:
    workflow_id: str


WorkflowRuntimeCommand: TypeAlias = (
    StartAction
    | CloseSession
    | CancelSession
    | TogglePin
    | FollowUp
    | ActivateWorkflow
    | ReleaseForegroundWorkflow
    | NavigateWorkflowBack
    | WorkflowInvocationFailed
    | HeadlessWorkflowFinished
)


@dataclass(frozen=True)
class _WorkflowRecord:
    controller: WorkflowController
    binding: ProviderExecutionBinding
    presentation: WorkflowPresentation


class _HeadlessPresenter:
    def __init__(self, on_failed: Callable[[str], None]) -> None:
        self._on_failed = on_failed

    def render(self, snapshot: SessionSnapshot) -> None:
        if snapshot.status == SessionStatus.FAILED:
            self._on_failed(snapshot.error)


class WorkflowRuntimeModule:
    """Owns desktop coordination for workflow commands and workflow identities."""

    def __init__(
        self,
        *,
        actions: ActionCatalog,
        shortcuts: ShortcutCatalog,
        execute_action: ActionExecutor,
        view: ApplicationView,
        supervisor: TaskSupervisor,
        enqueue: Callable[[object], None],
        provider_configuration: ProviderConfigurationCoordinator,
        workflow_context_reader: WorkflowContextReader,
        incident_reporter: IncidentReporter,
        operation_tracker: OperationTracker | None = None,
        notifier: UserNotifier | None = None,
        speech_coordinator: SpeechCoordinator | None = None,
        input_targets: InputTargetResolver | None = None,
        shortcut_intents: ShortcutIntentCoordinator | None = None,
    ) -> None:
        self._actions = actions
        self._execute_action = execute_action
        self._view = view
        self._supervisor = supervisor
        self._enqueue = enqueue
        self._provider_configuration = provider_configuration
        self._workflow_context_reader = workflow_context_reader
        self._incident_reporter = incident_reporter
        self._operation_tracker = operation_tracker
        self._notifier = notifier
        self._speech_coordinator = speech_coordinator
        self._input_targets = input_targets or InputTargetResolver()
        self._records: dict[str, _WorkflowRecord] = {}
        self._foreground_id: str | None = None
        self._shortcut_intents = shortcut_intents or ShortcutSequenceCoordinator(
            shortcuts,
            on_waiting=self._sequence_waiting,
            on_error=self._sequence_error,
            on_cancel_active=self._cancel_headless_workflows,
        )

    def controller_for(self, workflow_id: str) -> WorkflowController | None:
        record = self._records.get(workflow_id)
        return record.controller if record is not None else None

    def has_foreground_workflow(self) -> bool:
        return self._foreground_id in self._records

    def resolve_shortcut(self, command: ShortcutTriggered) -> AppCommand | None:
        return self._shortcut_intents.resolve(command)

    def cancel_shortcut_sequence(self) -> None:
        self._shortcut_intents.cancel()

    def cancel_active_operations(self) -> tuple[str, ...]:
        self._shortcut_intents.cancel()
        task_ids: list[str] = []
        for workflow_id, record in tuple(self._records.items()):
            active_id = record.controller.snapshot.active_invocation_id
            if record.presentation == "headless":
                if active_id is not None:
                    task_ids.append(active_id)
                self._end(
                    workflow_id,
                    "cancel",
                    cancel_task=False,
                )
                if self._speech_coordinator is not None:
                    self._speech_coordinator.cancel_workflow(workflow_id)
                continue
            stopped_id = record.controller.stop_active()
            if stopped_id is not None:
                task_ids.append(stopped_id)
        return tuple(task_ids)

    def handle(self, command: WorkflowRuntimeCommand) -> None:
        if isinstance(command, StartAction):
            self._start_action(command)
        elif isinstance(command, CloseSession):
            self._close(command.session_id)
        elif isinstance(command, CancelSession):
            self._cancel(command.session_id)
        elif isinstance(command, TogglePin):
            controller = self.controller_for(command.session_id)
            if controller and controller.snapshot.status not in {SessionStatus.CANCELLED, SessionStatus.CLOSED}:
                controller.toggle_pin()
        elif isinstance(command, FollowUp):
            self._follow_up(command)
        elif isinstance(command, ActivateWorkflow):
            record = self._records.get(command.workflow_id)
            if record is not None and record.presentation == "visible":
                self._foreground_id = command.workflow_id
        elif isinstance(command, ReleaseForegroundWorkflow):
            if self._foreground_id == command.workflow_id:
                self._foreground_id = None
        elif isinstance(command, NavigateWorkflowBack):
            controller = self.controller_for(command.workflow_id)
            if controller is not None:
                controller.navigate_back()
        elif isinstance(command, WorkflowInvocationFailed):
            self._handle_unhandled(command.workflow_id, command.error)
        elif isinstance(command, HeadlessWorkflowFinished):
            self._finish_headless(command.workflow_id)

    def stop(self) -> None:
        self._shortcut_intents.cancel()
        self._cancel_headless_workflows()
        for workflow_id in tuple(self._records):
            self._end(workflow_id, "cancel")

    def show_last_error(self) -> None:
        error = self._operation_tracker.last_error if self._operation_tracker is not None else None
        if error is not None and self._notifier is not None:
            self._notifier.notify("ClipAI — Last Error", " ".join(part for part in (error.message, error.suggestion) if part))

    def _start_action(self, command: StartAction) -> None:
        action = self._actions.resolve(command.action_id, command.press_type)
        if command.result_route == "speech":
            self._start_headless_action(action, command)
            return
        context = self._foreground_context()
        target = self._input_targets.resolve(context, action.external_fallback)
        contextual = target.kind == "workflow_result" and target.document is not None
        if contextual:
            assert context is not None
            workflow_id = context.workflow_id
            record = self._records[workflow_id]
            controller = record.controller
            parent_step_id = context.step_id
            active_id = controller.snapshot.active_invocation_id
            if active_id is not None:
                controller.cancel_active()
                self._supervisor.cancel(active_id)
        else:
            previous = self.controller_for(self._foreground_id or "")
            if previous is not None and not previous.snapshot.pinned:
                self._end(previous.snapshot.session_id, "cancel")
            workflow_id = uuid.uuid4().hex
            target = InputTarget("external_text")
            parent_step_id = None
            controller = WorkflowController(
                SessionSnapshot(workflow_id, 0, SessionStatus.CREATED, action.id, action.name, self._provider_configuration.active_binding.model),
                self._view,
            )
            record = self._register(
                workflow_id,
                controller,
                self._provider_configuration.active_binding,
                "visible",
            )
        invocation = ActionInvocation(
            uuid.uuid4().hex,
            action.id,
            command.press_type,
            target,
            workflow_id=workflow_id,
            parent_step_id=parent_step_id,
        )
        controller.begin_invocation(invocation, action)
        self._foreground_id = workflow_id
        self._submit_invocation(
            workflow_id,
            invocation.invocation_id,
            lambda: self._execute_action.execute_invocation(action, invocation, controller, binding=record.binding),
        )

    def _start_headless_action(self, action, command: StartAction) -> None:
        context = self._foreground_context()
        target = self._input_targets.resolve(context, action.external_fallback)
        workflow_id = uuid.uuid4().hex
        controller = WorkflowController(
            SessionSnapshot(workflow_id, 0, SessionStatus.CREATED, action.id, action.name, self._provider_configuration.active_binding.model),
            _HeadlessPresenter(lambda message: self._sequence_error(message, "Check the active model and try again.")),
        )
        invocation = ActionInvocation(
            uuid.uuid4().hex,
            action.id,
            command.press_type,
            target,
            result_route="speech",
            workflow_id=workflow_id,
        )
        controller.begin_invocation(invocation, action)
        record = self._register(
            workflow_id,
            controller,
            self._provider_configuration.active_binding,
            "headless",
        )

        def execute() -> None:
            self._execute_action.execute_invocation(action, invocation, controller, binding=record.binding)
            if controller.snapshot.status in {SessionStatus.COMPLETED, SessionStatus.FAILED}:
                self._enqueue(HeadlessWorkflowFinished(workflow_id))

        self._submit_invocation(workflow_id, invocation.invocation_id, execute)

    def _cancel_headless_workflows(self) -> None:
        workflow_ids = tuple(
            workflow_id
            for workflow_id, record in self._records.items()
            if record.presentation == "headless"
        )
        for workflow_id in workflow_ids:
            self._end(workflow_id, "cancel")
            if self._speech_coordinator is not None:
                self._speech_coordinator.cancel_workflow(workflow_id)

    def _follow_up(self, command: FollowUp) -> None:
        record = self._records.get(command.session_id)
        if record is None or record.presentation != "visible" or not command.text.strip():
            return
        controller = record.controller
        previous = controller.snapshot
        if previous.displayed_step_index < 0:
            return
        parent = previous.steps[previous.displayed_step_index]
        action = self._actions.resolve(parent.action_id, parent.press_type)
        invocation = ActionInvocation(
            uuid.uuid4().hex,
            action.id,
            action.press_type,
            InputTarget("workflow_result", InputDocument(command.text.strip(), "workflow_result", command.session_id, parent.step_id)),
            workflow_id=command.session_id,
            parent_step_id=parent.step_id,
        )
        controller.begin_invocation(invocation, action)
        self._submit_invocation(
            command.session_id,
            invocation.invocation_id,
            lambda: self._execute_action.execute_follow_up_invocation(
                action,
                command.text.strip(),
                invocation,
                controller,
                original_input=previous.original_input,
                previous_result=parent.result_text,
                binding=record.binding,
            ),
        )

    def _cancel(self, session_id: str) -> None:
        self._end(session_id, "cancel")

    def _close(self, session_id: str) -> None:
        self._end(session_id, "close")

    def _handle_unhandled(self, session_id: str, error: BaseException) -> None:
        incident_id = self._incident_reporter.report(error, context=f"session:{session_id}")
        record = self._records.get(session_id)
        controller = record.controller if record is not None else None
        if controller:
            active_id = controller.snapshot.active_invocation_id
            if active_id is not None:
                controller.fail(active_id, f"ClipAI encountered an unexpected error. Incident: {incident_id}")
            if record is not None and record.presentation == "headless":
                self._end(session_id, "release")

    def _submit_invocation(
        self,
        workflow_id: str,
        invocation_id: str,
        work: Callable[[], None],
    ) -> None:
        try:
            self._supervisor.submit(
                invocation_id,
                work,
                lambda error: self._enqueue(WorkflowInvocationFailed(workflow_id, error)),
            )
        except BaseException as error:
            self._handle_unhandled(workflow_id, error)

    def _finish_headless(self, workflow_id: str) -> None:
        record = self._records.get(workflow_id)
        if record is not None and record.presentation == "headless":
            self._end(workflow_id, "release")

    def _foreground_context(self):
        workflow_id = self._foreground_id
        if workflow_id is None:
            return None
        record = self._records.get(workflow_id)
        if record is None or record.presentation != "visible":
            self._foreground_id = None
            return None
        context = self._workflow_context_reader.workflow_context(workflow_id)
        return context if context is not None and context.workflow_id == workflow_id else None

    def _register(
        self,
        workflow_id: str,
        controller: WorkflowController,
        binding: ProviderExecutionBinding,
        presentation: WorkflowPresentation,
    ) -> _WorkflowRecord:
        if workflow_id in self._records:
            raise RuntimeError(f"workflow identity is already registered: {workflow_id}")
        record = _WorkflowRecord(controller, binding, presentation)
        self._records[workflow_id] = record
        return record

    def _end(
        self,
        workflow_id: str,
        disposition: Literal["cancel", "close", "release"],
        *,
        cancel_task: bool = True,
    ) -> None:
        record = self._records.pop(workflow_id, None)
        if record is None:
            return
        if self._foreground_id == workflow_id:
            self._foreground_id = None
        active_id = record.controller.snapshot.active_invocation_id
        if disposition == "cancel":
            record.controller.cancel()
        elif disposition == "close":
            record.controller.close()
        if active_id is not None and cancel_task:
            self._supervisor.cancel(active_id)

    def _sequence_waiting(self) -> None:
        if self._operation_tracker is not None:
            self._operation_tracker.report_waiting()

    def _sequence_error(self, message: str, suggestion: str) -> None:
        if self._operation_tracker is not None:
            self._operation_tracker.report_error(message, suggestion)
        if self._notifier is not None:
            self._notifier.notify("ClipAI", " ".join(part for part in (message, suggestion) if part))
