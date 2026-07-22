from __future__ import annotations

from collections.abc import Callable
from typing import TypeAlias
import uuid

from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.commands import ActivateWorkflow, AppCommand, CancelSession, CloseSession, FollowUp, NavigateWorkflowBack, ShortcutTriggered, StartAction, TogglePin
from ClipAI.core.models import ActionInvocation, InputDocument, InputTarget
from ClipAI.core.ports import ActiveWorkflowContextReader, ApplicationView, OperationTracker, UserNotifier
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
from ClipAI.services.workflow_registry import WorkflowRegistry
from ClipAI.support.diagnostics import IncidentReporter


WorkflowRuntimeCommand: TypeAlias = StartAction | CloseSession | CancelSession | TogglePin | FollowUp | ActivateWorkflow | NavigateWorkflowBack


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
        provider_configuration: ProviderConfigurationCoordinator,
        workflow_context_reader: ActiveWorkflowContextReader,
        incident_reporter: IncidentReporter,
        operation_tracker: OperationTracker | None = None,
        notifier: UserNotifier | None = None,
        speech_coordinator: SpeechCoordinator | None = None,
        input_targets: InputTargetResolver | None = None,
        shortcut_intents: ShortcutIntentCoordinator | None = None,
        registry: WorkflowRegistry | None = None,
    ) -> None:
        self._actions = actions
        self._execute_action = execute_action
        self._view = view
        self._supervisor = supervisor
        self._provider_configuration = provider_configuration
        self._workflow_context_reader = workflow_context_reader
        self._incident_reporter = incident_reporter
        self._operation_tracker = operation_tracker
        self._notifier = notifier
        self._speech_coordinator = speech_coordinator
        self._input_targets = input_targets or InputTargetResolver()
        self._registry = registry or WorkflowRegistry()
        self._provider_bindings: dict[str, ProviderExecutionBinding] = {}
        self._shortcut_intents = shortcut_intents or ShortcutSequenceCoordinator(
            shortcuts,
            on_waiting=self._sequence_waiting,
            on_error=self._sequence_error,
            on_cancel_active=self._cancel_sequence,
        )

    @property
    def registry(self) -> WorkflowRegistry:
        return self._registry

    @property
    def workflows(self) -> dict[str, WorkflowController]:
        return self._registry.workflows

    @property
    def foreground_id(self) -> str | None:
        return self._registry.foreground_id

    @property
    def sequence_id(self) -> str | None:
        return self._registry.sequence_id

    def resolve_shortcut(self, command: ShortcutTriggered) -> AppCommand | None:
        return self._shortcut_intents.resolve(command)

    def handle(self, command: WorkflowRuntimeCommand) -> None:
        if isinstance(command, StartAction):
            self._start_action(command)
        elif isinstance(command, CloseSession):
            self._close(command.session_id)
        elif isinstance(command, CancelSession):
            self._cancel(command.session_id)
        elif isinstance(command, TogglePin):
            controller = self.workflows.get(command.session_id)
            if controller and controller.snapshot.status not in {SessionStatus.CANCELLED, SessionStatus.CLOSED}:
                controller.toggle_pin()
        elif isinstance(command, FollowUp):
            self._follow_up(command)
        elif isinstance(command, ActivateWorkflow):
            self._registry.activate(command.workflow_id)
        elif isinstance(command, NavigateWorkflowBack):
            controller = self.workflows.get(command.workflow_id)
            if controller is not None:
                controller.navigate_back()

    def stop(self) -> None:
        self._shortcut_intents.cancel()
        self._cancel_sequence()
        for controller in list(self.workflows.values()):
            controller.cancel()

    def show_last_error(self) -> None:
        error = self._operation_tracker.last_error if self._operation_tracker is not None else None
        if error is not None and self._notifier is not None:
            self._notifier.notify("ClipAI — Last Error", " ".join(part for part in (error.message, error.suggestion) if part))

    def _start_action(self, command: StartAction) -> None:
        action = self._actions.resolve(command.action_id, command.press_type)
        if command.result_route == "speech":
            self._start_sequence_action(action, command)
            return
        context = self._workflow_context_reader.active_workflow_context()
        if context is not None and context.workflow_id not in self.workflows:
            context = None
        target = self._input_targets.resolve(context, action.external_fallback)
        contextual = target.kind == "workflow_result" and target.document is not None
        if contextual:
            assert context is not None
            workflow_id = context.workflow_id
            controller = self.workflows[workflow_id]
            parent_step_id = context.step_id
            active_id = controller.snapshot.active_invocation_id
            if active_id is not None:
                controller.cancel_active()
                self._supervisor.cancel(active_id)
        else:
            previous = self._registry.get(self._registry.foreground_id)
            if previous is not None and not previous.snapshot.pinned:
                previous_id = previous.snapshot.session_id
                active_id = previous.snapshot.active_invocation_id
                previous.cancel()
                if active_id is not None:
                    self._supervisor.cancel(active_id)
                self._registry.remove(previous_id)
                self._provider_bindings.pop(previous_id, None)
            workflow_id = uuid.uuid4().hex
            target = InputTarget("external_text")
            parent_step_id = None
            controller = WorkflowController(
                SessionSnapshot(workflow_id, 0, SessionStatus.CREATED, action.id, action.name, self._provider_configuration.active_binding.model),
                self._view,
            )
            self._registry.add(workflow_id, controller)
            self._provider_bindings[workflow_id] = self._provider_configuration.active_binding
        invocation = ActionInvocation(
            uuid.uuid4().hex,
            action.id,
            command.press_type,
            target,
            workflow_id=workflow_id,
            parent_step_id=parent_step_id,
        )
        controller.begin_invocation(invocation, action)
        self._registry.foreground_id = workflow_id
        binding = self._provider_bindings[workflow_id]
        self._supervisor.submit(
            invocation.invocation_id,
            lambda: self._execute_action.execute_invocation(action, invocation, controller, binding=binding),
            lambda error: self._handle_unhandled(workflow_id, error),
        )

    def _start_sequence_action(self, action, command: StartAction) -> None:
        self._cancel_sequence()
        context = self._workflow_context_reader.active_workflow_context()
        if context is not None and context.workflow_id not in self.workflows:
            context = None
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
        self._registry.add(workflow_id, controller)
        self._provider_bindings[workflow_id] = self._provider_configuration.active_binding
        self._registry.sequence_id = workflow_id
        binding = self._provider_bindings[workflow_id]

        def execute() -> None:
            self._execute_action.execute_invocation(action, invocation, controller, binding=binding)
            if controller.snapshot.status == SessionStatus.COMPLETED and self._registry.sequence_id == workflow_id:
                self._registry.remove(workflow_id)
                self._provider_bindings.pop(workflow_id, None)

        self._supervisor.submit(invocation.invocation_id, execute, lambda error: self._handle_unhandled(workflow_id, error))

    def _cancel_sequence(self) -> None:
        workflow_id = self._registry.sequence_id
        self._registry.sequence_id = None
        if workflow_id is None:
            return
        controller = self._registry.remove(workflow_id)
        self._provider_bindings.pop(workflow_id, None)
        if controller is not None:
            active_id = controller.snapshot.active_invocation_id
            controller.cancel()
            if active_id:
                self._supervisor.cancel(active_id)
        if self._speech_coordinator is not None:
            self._speech_coordinator.cancel_workflow(workflow_id)

    def _follow_up(self, command: FollowUp) -> None:
        controller = self.workflows.get(command.session_id)
        if controller is None or not command.text.strip():
            return
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
        binding = self._provider_bindings[command.session_id]
        self._supervisor.submit(
            invocation.invocation_id,
            lambda: self._execute_action.execute_follow_up_invocation(
                action,
                command.text.strip(),
                invocation,
                controller,
                original_input=previous.original_input,
                previous_result=parent.result_text,
                binding=binding,
            ),
            lambda error: self._handle_unhandled(command.session_id, error),
        )

    def _cancel(self, session_id: str) -> None:
        controller = self.workflows.get(session_id)
        if controller:
            active_id = controller.snapshot.active_invocation_id
            controller.cancel()
            if active_id is not None:
                self._supervisor.cancel(active_id)

    def _close(self, session_id: str) -> None:
        controller = self._registry.remove(session_id)
        self._provider_bindings.pop(session_id, None)
        if controller:
            active_id = controller.snapshot.active_invocation_id
            controller.close()
            if active_id is not None:
                self._supervisor.cancel(active_id)

    def _handle_unhandled(self, session_id: str, error: BaseException) -> None:
        incident_id = self._incident_reporter.report(error, context=f"session:{session_id}")
        controller = self.workflows.get(session_id)
        if controller:
            active_id = controller.snapshot.active_invocation_id
            if active_id is not None:
                controller.fail(active_id, f"ClipAI encountered an unexpected error. Incident: {incident_id}")

    def _sequence_waiting(self) -> None:
        if self._operation_tracker is not None:
            self._operation_tracker.report_waiting()

    def _sequence_error(self, message: str, suggestion: str) -> None:
        if self._operation_tracker is not None:
            self._operation_tracker.report_error(message, suggestion)
        if self._notifier is not None:
            self._notifier.notify("ClipAI", " ".join(part for part in (message, suggestion) if part))
