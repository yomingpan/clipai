from __future__ import annotations

from collections.abc import Callable
import logging
import queue
import uuid

from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.commands import ActivateWorkflow, AppCommand, ArchiveResult, CancelSession, CloseSession, CopyResult, ExportDiagnostics, FollowUp, NavigateWorkflowBack, PasteResult, ShortcutTriggered, ShutdownApplication, SpeakSelectionOrClipboard, StartAction, TogglePin, ToggleSpeech
from ClipAI.core.models import ActionInvocation, InputDocument, InputTarget
from ClipAI.core.ports import ActiveWorkflowContextReader, ApplicationView, DiagnosticsExporter, OperationHandle, OperationTracker, UserNotifier
from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.services.action_catalog import ActionCatalog
from ClipAI.services.execute_action import ActionExecutor
from ClipAI.services.output_actions import OutputActions
from ClipAI.services.input_target_resolver import InputTargetResolver
from ClipAI.services.shortcut_catalog import ShortcutCatalog
from ClipAI.services.shortcut_intent import ShortcutIntentCoordinator
from ClipAI.services.speech_coordinator import SpeechCoordinator
from ClipAI.services.workflow_controller import WorkflowController
from ClipAI.support.diagnostics import IncidentReporter

logger = logging.getLogger("clipai.runtime")


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
        model: str,
        hotkey_registrar: Callable[[dict[str, dict[str, str]], Callable[[str, str], None]], object],
        tray_factory: Callable[[Callable[[], None]], object] | None = None,
        operation_tracker: OperationTracker | None = None,
        diagnostics_exporter: DiagnosticsExporter | None = None,
        notifier: UserNotifier | None = None,
        incident_reporter: IncidentReporter | None = None,
        speech_coordinator: SpeechCoordinator | None = None,
        workflow_context_reader: ActiveWorkflowContextReader | None = None,
        shortcut_intents: ShortcutIntentCoordinator | None = None,
        input_targets: InputTargetResolver | None = None,
    ) -> None:
        self._actions = actions
        self._shortcuts = shortcuts
        self._execute_action = execute_action
        self._output_actions = output_actions
        self._view = view
        self._supervisor = supervisor
        self._model = model
        self._hotkey_registrar = hotkey_registrar
        self._tray_factory = tray_factory
        self._operation_tracker = operation_tracker
        self._diagnostics_exporter = diagnostics_exporter
        self._notifier = notifier
        self._incident_reporter = incident_reporter or IncidentReporter(logger)
        self._speech_coordinator = speech_coordinator
        self._workflow_context_reader = workflow_context_reader or (view if hasattr(view, "active_workflow_context") else None)  # type: ignore[assignment]
        self._shortcut_intents = shortcut_intents or ShortcutIntentCoordinator(shortcuts)
        self._input_targets = input_targets or InputTargetResolver()
        self._commands: queue.Queue[AppCommand] = queue.Queue()
        self._workflows: dict[str, WorkflowController] = {}
        self._speech_operations: dict[str, OperationHandle] = {}
        self._popup_speech_ids: dict[str, str] = {}
        self._foreground_id: str | None = None
        self._listener: object | None = None
        self._tray: object | None = None
        self._stopping = False
        self._view.set_command_sink(self.enqueue)

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
            if hasattr(self._tray, "start"):
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
        for controller in list(self._workflows.values()):
            controller.cancel()
        for operation in list(self._speech_operations.values()):
            operation.cancel()
        self._speech_operations.clear()
        self._popup_speech_ids.clear()
        if self._speech_coordinator is not None:
            self._speech_coordinator.cancel_current()
        if self._listener is not None and hasattr(self._listener, "stop"):
            self._listener.stop()
        self._listener = None
        if self._tray is not None and hasattr(self._tray, "stop"):
            self._tray.stop()
        self._tray = None
        self._supervisor.shutdown()
        if self._operation_tracker is not None and hasattr(self._operation_tracker, "stop"):
            self._operation_tracker.stop()  # type: ignore[attr-defined]
        self._view.stop()

    def _handle(self, command: AppCommand) -> None:
        if isinstance(command, ShortcutTriggered):
            self._handle(self._shortcut_intents.resolve(command))
        elif isinstance(command, StartAction):
            self._start_action(command)
        elif isinstance(command, CloseSession):
            self._close(command.session_id)
        elif isinstance(command, CancelSession):
            self._cancel(command.session_id)
        elif isinstance(command, CopyResult):
            controller = self._workflows.get(command.session_id)
            if controller and controller.snapshot.content:
                self._output_actions.copy(command.text.strip() if command.text and command.text.strip() else controller.snapshot.content)
        elif isinstance(command, PasteResult):
            controller = self._workflows.get(command.session_id)
            if controller and controller.snapshot.content and self._output_actions.can_paste:
                text = command.text.strip() if command.text and command.text.strip() else controller.snapshot.content
                self._close(command.session_id)
                self._supervisor.submit(
                    f"paste:{command.session_id}",
                    lambda: self._output_actions.paste(text),
                    lambda error: logger.exception("Paste failed session_id=%s", command.session_id, exc_info=error),
                )
        elif isinstance(command, ArchiveResult):
            controller = self._workflows.get(command.session_id)
            if controller and controller.snapshot.content and self._output_actions.can_archive:
                self._output_actions.archive(controller.snapshot.content)
        elif isinstance(command, TogglePin):
            controller = self._workflows.get(command.session_id)
            if controller and controller.snapshot.status not in {SessionStatus.CANCELLED, SessionStatus.CLOSED}:
                controller.toggle_pin()
        elif isinstance(command, FollowUp):
            self._follow_up(command)
        elif isinstance(command, ShutdownApplication):
            self.stop()
        elif isinstance(command, ToggleSpeech):
            self._toggle_speech(command.session_id, command.text)
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

    def _speak_selection_or_clipboard(self) -> None:
        if self._speech_coordinator is None:
            return
        job = self._speech_coordinator.create_job(clipboard_only=self._has_active_workflows())
        self._supervisor.submit(
            f"speech:{job.operation_id}",
            job.run,
            lambda error: self._handle_speech_error(job.operation_id, error),
        )

    def _has_active_workflows(self) -> bool:
        return bool(self._workflows)

    def _start_action(self, command: StartAction) -> None:
        action = self._actions.resolve(command.action_id, command.press_type)
        context = self._workflow_context_reader.active_workflow_context() if self._workflow_context_reader is not None else None
        if context is not None and context.workflow_id not in self._workflows:
            context = None
        target = self._input_targets.resolve(action.input_policy, context)
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
        self._supervisor.submit(
            invocation.invocation_id,
            lambda: self._execute_action.execute_invocation(action, invocation, controller),
            lambda error: self._handle_unhandled(workflow_id, error),
        )

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
        self._supervisor.submit(
            invocation.invocation_id,
            lambda: self._execute_action.execute_follow_up_invocation(
                action,
                command.text.strip(),
                invocation,
                controller,
                original_input=previous.original_input,
                previous_result=parent.result_text,
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

    def _toggle_speech(self, session_id: str, selected_text: str | None = None) -> None:
        controller = self._workflows.get(session_id)
        if controller is None or not controller.snapshot.content or not self._output_actions.can_speak:
            return
        if controller.snapshot.speaking:
            self._output_actions.stop_speech()
            controller.set_speaking(False)
            operation_id = self._popup_speech_ids.pop(session_id, None)
            if operation_id is not None:
                self._supervisor.cancel(operation_id)
            operation = self._speech_operations.pop(session_id, None)
            if operation is not None:
                operation.cancel()
            return
        if self._speech_coordinator is not None:
            self._speech_coordinator.cancel_current()
        controller.set_speaking(True)
        text = selected_text.strip() if selected_text and selected_text.strip() else controller.snapshot.content
        operation_id = f"speech:{session_id}:{uuid.uuid4().hex}"
        self._popup_speech_ids[session_id] = operation_id
        operation = self._operation_tracker.start(f"tts:{operation_id}", "tts") if self._operation_tracker else None
        if operation is not None:
            self._speech_operations[session_id] = operation

        def speak() -> None:
            try:
                self._output_actions.speak(text)
                if operation is not None:
                    operation.succeed()
            except BaseException:
                if operation is not None:
                    operation.fail()
                raise
            finally:
                if self._popup_speech_ids.get(session_id) == operation_id:
                    self._popup_speech_ids.pop(session_id, None)
                    self._speech_operations.pop(session_id, None)
                    controller.set_speaking(False)

        self._supervisor.submit(
            operation_id,
            speak,
            lambda error: self._handle_speech_error(session_id, error),
        )

    def _close(self, session_id: str) -> None:
        controller = self._workflows.pop(session_id, None)
        if controller:
            self._output_actions.stop_speech()
            operation_id = self._popup_speech_ids.pop(session_id, None)
            if operation_id is not None:
                self._supervisor.cancel(operation_id)
            operation = self._speech_operations.pop(session_id, None)
            if operation is not None:
                operation.cancel()
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
