from __future__ import annotations

from collections.abc import Callable
import logging
import queue
import uuid

from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.commands import ActivateWorkflow, AppCommand, ArchiveResult, CancelSession, CloseSession, CopyResult, ExportDiagnostics, FollowUp, NavigateWorkflowBack, PasteResult, SelectProviderModel, ShortcutTriggered, ShutdownApplication, SpeakSelectionOrClipboard, StartAction, TogglePin, ToggleSpeech
from ClipAI.core.models import ActionInvocation, InputDocument, InputTarget, ModelSelectionState, OutputOperationIntent
from ClipAI.core.ports import ActiveWorkflowContextReader, ApplicationView, DiagnosticsExporter, ModelPreferenceStore, ModelSelectionPresenter, OperationTracker, OutputOperationPresenter, RuntimeComponent, Stoppable, UserNotifier
from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.services.action_catalog import ActionCatalog
from ClipAI.services.execute_action import ActionExecutor
from ClipAI.services.output_actions import OutputActions
from ClipAI.services.provider_binding import ProviderExecutionBinding
from ClipAI.services.output_operation import OutputOperationCoordinator
from ClipAI.services.input_target_resolver import InputTargetResolver
from ClipAI.services.shortcut_catalog import ShortcutCatalog
from ClipAI.services.shortcut_intent import ShortcutIntentCoordinator
from ClipAI.services.shortcut_sequence import ShortcutSequenceCoordinator
from ClipAI.services.speech_coordinator import SpeechCoordinator
from ClipAI.services.workflow_controller import WorkflowController
from ClipAI.services.workflow_registry import WorkflowRegistry
from ClipAI.support.diagnostics import IncidentReporter

logger = logging.getLogger("clipai.runtime")


class _HeadlessPresenter:
    def __init__(self, on_failed: Callable[[str], None]) -> None:
        self._on_failed = on_failed

    def render(self, snapshot: SessionSnapshot) -> None:
        if snapshot.status == SessionStatus.FAILED:
            self._on_failed(snapshot.error)


class AppRuntime:
    def __init__(
        self,
        *,
        actions: ActionCatalog,
        shortcuts: ShortcutCatalog,
        execute_action: ActionExecutor,
        output_actions: OutputActions,
        view: ApplicationView,
        supervisor: TaskSupervisor,
        provider_binding: ProviderExecutionBinding,
        hotkey_registrar: Callable[[dict[str, dict[str, str]], Callable[[str, str], None]], Stoppable],
        tray_factory: Callable[[Callable[[], None]], RuntimeComponent] | None = None,
        operation_tracker: OperationTracker | None = None,
        diagnostics_exporter: DiagnosticsExporter | None = None,
        notifier: UserNotifier | None = None,
        incident_reporter: IncidentReporter | None = None,
        speech_coordinator: SpeechCoordinator | None = None,
        workflow_context_reader: ActiveWorkflowContextReader,
        output_operation_presenter: OutputOperationPresenter,
        available_models: tuple[str, ...] = (),
        model_preferences: ModelPreferenceStore | None = None,
        model_selection_presenter: ModelSelectionPresenter | None = None,
        shortcut_intents: ShortcutIntentCoordinator | None = None,
        input_targets: InputTargetResolver | None = None,
    ) -> None:
        self._actions = actions
        self._shortcuts = shortcuts
        self._execute_action = execute_action
        self._output_actions = output_actions
        self._view = view
        self._supervisor = supervisor
        self._active_provider_binding = provider_binding
        self._model = provider_binding.model
        self._provider_name = provider_binding.provider_id
        self._available_models = available_models or (provider_binding.model,)
        self._model_preferences = model_preferences
        self._model_selection_presenter = model_selection_presenter
        self._hotkey_registrar = hotkey_registrar
        self._tray_factory = tray_factory
        self._operation_tracker = operation_tracker
        self._diagnostics_exporter = diagnostics_exporter
        self._notifier = notifier
        self._incident_reporter = incident_reporter or IncidentReporter(logger)
        self._speech_coordinator = speech_coordinator
        self._workflow_context_reader = workflow_context_reader
        self._output_operations = OutputOperationCoordinator(output_operation_presenter, operation_tracker)
        self._shortcut_intents = shortcut_intents or ShortcutSequenceCoordinator(
            shortcuts,
            on_waiting=self._sequence_waiting,
            on_error=self._sequence_error,
            on_cancel_active=self._cancel_sequence,
        )
        self._input_targets = input_targets or InputTargetResolver()
        self._commands: queue.Queue[AppCommand] = queue.Queue()
        self._workflow_registry = WorkflowRegistry()
        self._workflows = self._workflow_registry.workflows
        self._workflow_provider_bindings: dict[str, ProviderExecutionBinding] = {}
        self._listener: Stoppable | None = None
        self._tray: RuntimeComponent | None = None
        self._stopping = False
        self._view.set_command_sink(self.enqueue)

    @property
    def _foreground_id(self) -> str | None:
        return self._workflow_registry.foreground_id

    @_foreground_id.setter
    def _foreground_id(self, value: str | None) -> None:
        self._workflow_registry.foreground_id = value

    @property
    def _sequence_workflow_id(self) -> str | None:
        return self._workflow_registry.sequence_id

    @_sequence_workflow_id.setter
    def _sequence_workflow_id(self, value: str | None) -> None:
        self._workflow_registry.sequence_id = value

    def enqueue(self, command: object) -> None:
        if not self._stopping:
            self._commands.put(command)  # type: ignore[arg-type]

    def start(self) -> None:
        self._listener = self._hotkey_registrar(
            self._shortcuts.hotkey_map(),
            lambda shortcut_id, press_type: self.enqueue(ShortcutTriggered(shortcut_id, press_type)),
        )
        if self._tray_factory is not None:
            self._tray = self._tray_factory(lambda: self.enqueue(ShutdownApplication()))
            self._tray.start()

    def run_forever(self) -> None:
        self.start()
        try:
            self._view.run(self.drain_commands)
        finally:
            self.stop()

    def drain_commands(self) -> None:
        while True:
            try:
                command = self._commands.get_nowait()
            except queue.Empty:
                return
            self._handle(command)

    def stop(self) -> None:
        if self._stopping:
            return
        self._stopping = True
        self._shortcut_intents.cancel()
        self._cancel_sequence()
        for controller in list(self._workflows.values()):
            controller.cancel()
        if self._speech_coordinator is not None:
            self._speech_coordinator.cancel_current()
        if self._listener is not None:
            self._listener.stop()
        self._listener = None
        if self._tray is not None:
            self._tray.stop()
        self._tray = None
        self._supervisor.shutdown()
        if self._operation_tracker is not None:
            self._operation_tracker.stop()
        self._view.stop()

    def _handle(self, command: AppCommand) -> None:
        if isinstance(command, ShortcutTriggered):
            resolved = self._shortcut_intents.resolve(command)
            if resolved is not None:
                self._handle(resolved)
        elif isinstance(command, StartAction):
            self._start_action(command)
        elif isinstance(command, CloseSession):
            self._close(command.session_id)
        elif isinstance(command, CancelSession):
            self._cancel(command.session_id)
        elif isinstance(command, CopyResult):
            controller = self._workflows.get(command.session_id)
            if controller and controller.snapshot.content:
                text = command.text.strip() if command.text and command.text.strip() else controller.snapshot.content
                intent = OutputOperationIntent(command.operation_id or uuid.uuid4().hex, command.session_id, "copy", text)
                self._run_output_action(intent, lambda: self._output_actions.copy(text))
        elif isinstance(command, PasteResult):
            controller = self._workflows.get(command.session_id)
            if controller and controller.snapshot.content and self._output_actions.can_paste:
                text = command.text.strip() if command.text and command.text.strip() else controller.snapshot.content
                intent = OutputOperationIntent(command.operation_id or uuid.uuid4().hex, command.session_id, "paste", text)
                operation = self._output_operations.begin(intent)
                self._supervisor.submit(
                    intent.operation_id,
                    lambda: self._complete_paste(intent, operation),
                    lambda error: logger.error("Paste failed session_id=%s: %s", command.session_id, error),
                )
        elif isinstance(command, ArchiveResult):
            controller = self._workflows.get(command.session_id)
            if controller and controller.snapshot.content and self._output_actions.can_archive:
                text = command.text.strip() if command.text and command.text.strip() else controller.snapshot.content
                intent = OutputOperationIntent(command.operation_id or uuid.uuid4().hex, command.session_id, "archive", text)
                self._run_output_action(intent, lambda: self._output_actions.archive(text))
        elif isinstance(command, TogglePin):
            controller = self._workflows.get(command.session_id)
            if controller and controller.snapshot.status not in {SessionStatus.CANCELLED, SessionStatus.CLOSED}:
                controller.toggle_pin()
        elif isinstance(command, FollowUp):
            self._follow_up(command)
        elif isinstance(command, ShutdownApplication):
            self.stop()
        elif isinstance(command, ToggleSpeech):
            self._toggle_speech(command.session_id, command.text, command.operation_id)
        elif isinstance(command, ExportDiagnostics):
            self._export_diagnostics()
        elif isinstance(command, SpeakSelectionOrClipboard):
            self._speak_selection_or_clipboard()
        elif isinstance(command, ActivateWorkflow):
            if command.workflow_id in self._workflows:
                self._foreground_id = command.workflow_id
        elif isinstance(command, NavigateWorkflowBack):
            controller = self._workflows.get(command.workflow_id)
            if controller is not None:
                controller.navigate_back()
        elif isinstance(command, SelectProviderModel):
            self._select_provider_model(command)

    def _model_selection(self) -> ModelSelectionState:
        return ModelSelectionState(self._provider_name, self._available_models, self._model)

    def _select_provider_model(self, command: SelectProviderModel) -> None:
        if self._model_selection_presenter is None or self._model_preferences is None:
            return
        if command.provider != self._provider_name or command.model not in self._available_models:
            self._model_selection_presenter.set_model_selection(self._model_selection())
            if self._operation_tracker is not None:
                self._operation_tracker.report_error("Model switch rejected.", "Choose a model listed for the active provider.")
            return
        if command.model == self._model:
            self._model_selection_presenter.set_model_selection(self._model_selection())
            return
        try:
            self._model_preferences.save_model(f"{self._provider_name.upper()}_MODEL", command.model)
        except OSError:
            self._model_selection_presenter.set_model_selection(self._model_selection())
            if self._operation_tracker is not None:
                self._operation_tracker.report_error("Could not save the model selection.", "The previous model remains active. Check .env permissions and try again.")
            return
        self._model = command.model
        self._active_provider_binding = ProviderExecutionBinding(
            provider=self._active_provider_binding.provider,
            provider_id=self._active_provider_binding.provider_id,
            model=command.model,
            readiness_issues=self._active_provider_binding.readiness_issues,
        )
        self._model_selection_presenter.set_model_selection(self._model_selection())

    def _speak_selection_or_clipboard(self) -> None:
        if self._speech_coordinator is None:
            return
        self._cancel_current_speech_projection()
        job = self._speech_coordinator.create_job(clipboard_only=self._has_active_workflows())
        intent = OutputOperationIntent(job.operation_id, job.workflow_id, "speech", "")
        operation = self._output_operations.begin(intent)
        self._supervisor.submit(
            f"speech:{job.operation_id}",
            lambda: self._run_speech_job(job, intent, operation, None),
            lambda error: self._handle_speech_error(job.operation_id, error),
        )

    def _has_active_workflows(self) -> bool:
        return bool(self._workflows)

    def _start_action(self, command: StartAction) -> None:
        action = self._actions.resolve(command.action_id, command.press_type)
        if command.result_route == "speech":
            self._start_sequence_action(action, command)
            return
        context = self._workflow_context_reader.active_workflow_context()
        if context is not None and context.workflow_id not in self._workflows:
            context = None
        target = self._input_targets.resolve(context, action.external_fallback)
        contextual = target.kind == "workflow_result" and target.document is not None
        if contextual:
            assert context is not None
            workflow_id = context.workflow_id
            controller = self._workflows[workflow_id]
            parent_step_id = context.step_id
            active_id = controller.snapshot.active_invocation_id
            if active_id is not None:
                controller.cancel_active()
                self._supervisor.cancel(active_id)
        else:
            previous = self._workflows.get(self._foreground_id or "")
            if previous is not None and not previous.snapshot.pinned:
                previous_id = previous.snapshot.session_id
                active_id = previous.snapshot.active_invocation_id
                previous.cancel()
                if active_id is not None:
                    self._supervisor.cancel(active_id)
                self._workflows.pop(previous_id, None)
            workflow_id = uuid.uuid4().hex
            target = InputTarget("external_text")
            parent_step_id = None
            controller = WorkflowController(
                SessionSnapshot(
                    session_id=workflow_id,
                    revision=0,
                    status=SessionStatus.CREATED,
                    action_id=action.id,
                    title=action.name,
                    model=self._model,
                ),
                self._view,
            )
            self._workflows[workflow_id] = controller
            self._workflow_provider_bindings[workflow_id] = self._active_provider_binding
        invocation = ActionInvocation(
            invocation_id=uuid.uuid4().hex,
            action_id=action.id,
            press_type=command.press_type,
            input_target=target,
            workflow_id=workflow_id,
            parent_step_id=parent_step_id,
        )
        controller.begin_invocation(invocation, action)
        self._foreground_id = workflow_id
        binding = self._workflow_provider_bindings[workflow_id]
        self._supervisor.submit(
            invocation.invocation_id,
            lambda: self._execute_action.execute_invocation(action, invocation, controller, binding=binding),
            lambda error: self._handle_unhandled(workflow_id, error),
        )

    def _run_output_action(self, intent: OutputOperationIntent, work: Callable[[], None]) -> None:
        operation = self._output_operations.begin(intent)
        self._supervisor.submit(
            intent.operation_id,
            lambda: self._complete_output_action(intent, operation, work),
            lambda error: logger.error("%s failed workflow_id=%s: %s", intent.kind, intent.workflow_id, error),
        )

    def _complete_output_action(self, intent, operation, work: Callable[[], None]) -> None:
        try:
            work()
        except BaseException as exc:
            self._output_operations.fail(intent, exc, operation)
            raise
        self._output_operations.succeed(intent, operation)

    def _complete_paste(self, intent, operation) -> None:
        try:
            self._output_actions.paste(intent.text)
        except BaseException as exc:
            self._output_operations.fail(intent, exc, operation)
            raise
        self._output_operations.succeed(intent, operation)
        self.enqueue(CloseSession(intent.workflow_id))

    def _start_sequence_action(self, action, command: StartAction) -> None:
        self._cancel_sequence()
        context = self._workflow_context_reader.active_workflow_context()
        if context is not None and context.workflow_id not in self._workflows:
            context = None
        target = self._input_targets.resolve(context, action.external_fallback)
        workflow_id = uuid.uuid4().hex
        controller = WorkflowController(
            SessionSnapshot(workflow_id, 0, SessionStatus.CREATED, action.id, action.name, self._model),
            _HeadlessPresenter(lambda message: self._sequence_error(message, "Check the active model and try again.")),
        )
        invocation = ActionInvocation(
            invocation_id=uuid.uuid4().hex,
            action_id=action.id,
            press_type=command.press_type,
            input_target=target,
            result_route="speech",
            workflow_id=workflow_id,
        )
        controller.begin_invocation(invocation, action)
        self._workflows[workflow_id] = controller
        self._workflow_provider_bindings[workflow_id] = self._active_provider_binding
        self._sequence_workflow_id = workflow_id
        binding = self._workflow_provider_bindings[workflow_id]
        def execute() -> None:
            self._execute_action.execute_invocation(action, invocation, controller, binding=binding)
            if controller.snapshot.status == SessionStatus.COMPLETED and self._sequence_workflow_id == workflow_id:
                self._workflows.pop(workflow_id, None)
                self._workflow_provider_bindings.pop(workflow_id, None)
                self._sequence_workflow_id = None

        self._supervisor.submit(invocation.invocation_id, execute, lambda error: self._handle_unhandled(workflow_id, error))

    def _cancel_sequence(self) -> None:
        workflow_id, self._sequence_workflow_id = self._sequence_workflow_id, None
        if workflow_id is None:
            return
        controller = self._workflows.pop(workflow_id, None)
        self._workflow_provider_bindings.pop(workflow_id, None)
        if controller is not None:
            active_id = controller.snapshot.active_invocation_id
            controller.cancel()
            if active_id:
                self._supervisor.cancel(active_id)
        if self._speech_coordinator is not None:
            self._speech_coordinator.cancel_workflow(workflow_id)

    def _sequence_waiting(self) -> None:
        if self._operation_tracker is not None:
            self._operation_tracker.report_waiting()

    def _sequence_error(self, message: str, suggestion: str) -> None:
        if self._operation_tracker is not None:
            self._operation_tracker.report_error(message, suggestion)
        if self._notifier is not None:
            self._notifier.notify("ClipAI", " ".join(part for part in (message, suggestion) if part))

    def show_last_error(self) -> None:
        error = self._operation_tracker.last_error if self._operation_tracker is not None else None
        if error is not None and self._notifier is not None:
            self._notifier.notify("ClipAI — Last Error", " ".join(part for part in (error.message, error.suggestion) if part))

    def _follow_up(self, command: FollowUp) -> None:
        controller = self._workflows.get(command.session_id)
        if controller is None or not command.text.strip():
            return
        previous = controller.snapshot
        if previous.displayed_step_index < 0:
            return
        parent = previous.steps[previous.displayed_step_index]
        action = self._actions.resolve(parent.action_id, parent.press_type)
        invocation = ActionInvocation(
            invocation_id=uuid.uuid4().hex,
            action_id=action.id,
            press_type=action.press_type,
            input_target=InputTarget("workflow_result", InputDocument(command.text.strip(), "workflow_result", command.session_id, parent.step_id)),
            workflow_id=command.session_id,
            parent_step_id=parent.step_id,
        )
        controller.begin_invocation(invocation, action)
        binding = self._workflow_provider_bindings[command.session_id]
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
        controller = self._workflows.get(session_id)
        if controller:
            active_id = controller.snapshot.active_invocation_id
            controller.cancel()
            if active_id is not None:
                self._supervisor.cancel(active_id)

    def _toggle_speech(self, session_id: str, selected_text: str | None = None, requested_operation_id: str = "") -> None:
        controller = self._workflows.get(session_id)
        if controller is None or not controller.snapshot.content or self._speech_coordinator is None:
            return
        if controller.snapshot.speaking:
            operation_id = self._speech_coordinator.operation_for(session_id)
            if operation_id is not None:
                self._speech_coordinator.cancel_operation(operation_id)
                self._supervisor.cancel(operation_id)
                self._output_operations.cancel(OutputOperationIntent(operation_id, session_id, "speech", ""))
            controller.set_speaking(False)
            return
        self._cancel_current_speech_projection()
        controller.set_speaking(True)
        text = selected_text.strip() if selected_text and selected_text.strip() else controller.snapshot.content
        operation_id = requested_operation_id or uuid.uuid4().hex
        intent = OutputOperationIntent(operation_id, session_id, "speech", text)
        operation = self._output_operations.begin(intent)
        job = self._speech_coordinator.create_text_job(operation_id=operation_id, workflow_id=session_id, text=text)

        self._supervisor.submit(
            operation_id,
            lambda: self._run_speech_job(job, intent, operation, controller),
            lambda error: self._handle_speech_error(session_id, error),
        )

    def _run_speech_job(self, job, intent, operation, controller) -> None:
        try:
            job.run()
        except BaseException as exc:
            current = self._output_operations.fail(intent, exc, operation)
            if current and controller is not None:
                controller.set_speaking(False)
            raise
        current = self._output_operations.succeed(intent, operation)
        if current and controller is not None:
            controller.set_speaking(False)

    def _cancel_current_speech_projection(self) -> None:
        if self._speech_coordinator is None:
            return
        identity = self._speech_coordinator.current_identity
        if identity is None:
            return
        operation_id, workflow_id = identity
        self._speech_coordinator.cancel_operation(operation_id)
        self._supervisor.cancel(operation_id)
        self._output_operations.cancel(OutputOperationIntent(operation_id, workflow_id, "speech", ""))
        previous = self._workflows.get(workflow_id)
        if previous is not None:
            previous.set_speaking(False)

    def _close(self, session_id: str) -> None:
        controller = self._workflows.pop(session_id, None)
        self._workflow_provider_bindings.pop(session_id, None)
        if controller:
            operation_id = self._speech_coordinator.operation_for(session_id) if self._speech_coordinator else None
            if operation_id is not None:
                self._speech_coordinator.cancel_operation(operation_id)
                self._supervisor.cancel(operation_id)
                self._output_operations.cancel(OutputOperationIntent(operation_id, session_id, "speech", ""))
            active_id = controller.snapshot.active_invocation_id
            controller.close()
            if active_id is not None:
                self._supervisor.cancel(active_id)
        if self._foreground_id == session_id:
            self._foreground_id = None

    def _handle_unhandled(self, session_id: str, error: BaseException) -> None:
        incident_id = self._incident_reporter.report(error, context=f"session:{session_id}")
        controller = self._workflows.get(session_id)
        if controller:
            active_id = controller.snapshot.active_invocation_id
            if active_id is not None:
                controller.fail(active_id, f"ClipAI encountered an unexpected error. Incident: {incident_id}")

    def _handle_speech_error(self, session_id: str, error: BaseException) -> None:
        self._incident_reporter.report(error, context=f"speech:{session_id}")
        controller = self._workflows.get(session_id)
        if controller:
            controller.set_speaking(False)

    def _export_diagnostics(self) -> None:
        if self._diagnostics_exporter is None:
            if self._notifier is not None:
                self._notifier.notify("ClipAI Diagnostics", "Diagnostics export is not configured.")
            return

        def export() -> None:
            destination = self._diagnostics_exporter.export()
            if self._notifier is not None:
                self._notifier.notify("ClipAI Diagnostics", f"Exported to {destination}")

        self._supervisor.submit(
            "diagnostics:export",
            export,
            self._handle_diagnostics_error,
        )

    def _handle_diagnostics_error(self, error: BaseException) -> None:
        incident_id = self._incident_reporter.report(error, context="diagnostics:export")
        if self._notifier is not None:
            self._notifier.notify("ClipAI Diagnostics", f"Export failed. Incident: {incident_id}")
