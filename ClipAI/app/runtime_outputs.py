from __future__ import annotations

from collections.abc import Callable
from typing import TypeAlias
import logging
import uuid

from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.commands import ArchiveResult, CloseSession, CopyResult, ExportDiagnostics, PasteResult, ReleaseForegroundWorkflow, SpeakSelectionOrClipboard, ToggleSpeech
from ClipAI.core.models import OutputOperationIntent, PasteTarget
from ClipAI.core.ports import DiagnosticsExporter, OperationTracker, OutputOperationPresenter, UserNotifier
from ClipAI.services.output_actions import OutputActions
from ClipAI.services.output_operation import OutputOperationCoordinator
from ClipAI.services.paste_target import PasteTargetCoordinator
from ClipAI.services.speech_coordinator import SpeechCoordinator
from ClipAI.services.workflow_controller import WorkflowController
from ClipAI.support.diagnostics import IncidentReporter

logger = logging.getLogger("clipai.runtime.outputs")

ResultOutputRuntimeCommand: TypeAlias = CopyResult | PasteResult | ArchiveResult | ToggleSpeech | SpeakSelectionOrClipboard | ExportDiagnostics


class ResultOutputRuntimeModule:
    """Owns output-operation scheduling, identity, and user-visible completion."""

    def __init__(
        self,
        *,
        output_actions: OutputActions,
        supervisor: TaskSupervisor,
        workflow_controller: Callable[[str], WorkflowController | None],
        has_foreground_workflow: Callable[[], bool],
        output_operation_presenter: OutputOperationPresenter,
        enqueue: Callable[[object], None],
        incident_reporter: IncidentReporter,
        operation_tracker: OperationTracker | None = None,
        diagnostics_exporter: DiagnosticsExporter | None = None,
        notifier: UserNotifier | None = None,
        speech_coordinator: SpeechCoordinator | None = None,
        paste_targets: PasteTargetCoordinator | None = None,
    ) -> None:
        self._output_actions = output_actions
        self._supervisor = supervisor
        self._workflow_controller = workflow_controller
        self._has_foreground_workflow = has_foreground_workflow
        self._enqueue = enqueue
        self._incident_reporter = incident_reporter
        self._operation_tracker = operation_tracker
        self._diagnostics_exporter = diagnostics_exporter
        self._notifier = notifier
        self._speech_coordinator = speech_coordinator
        self._paste_targets = paste_targets or PasteTargetCoordinator()
        self._operations = OutputOperationCoordinator(output_operation_presenter, operation_tracker)

    def observe_paste_target(self, target: PasteTarget) -> None:
        self._paste_targets.observe(target)

    def handle(self, command: ResultOutputRuntimeCommand) -> None:
        if isinstance(command, CopyResult):
            self._copy(command)
        elif isinstance(command, PasteResult):
            self._paste(command)
        elif isinstance(command, ArchiveResult):
            self._archive(command)
        elif isinstance(command, ToggleSpeech):
            self._toggle_speech(command.session_id, command.text, command.operation_id)
        elif isinstance(command, SpeakSelectionOrClipboard):
            self._speak_selection_or_clipboard()
        elif isinstance(command, ExportDiagnostics):
            self._export_diagnostics()

    def close_workflow(self, workflow_id: str) -> None:
        if self._speech_coordinator is None:
            return
        operation_id = self._speech_coordinator.operation_for(workflow_id)
        if operation_id is None:
            return
        self._speech_coordinator.cancel_operation(operation_id)
        self._supervisor.cancel(operation_id)
        self._operations.cancel(OutputOperationIntent(operation_id, workflow_id, "speech", ""))

    def stop(self) -> None:
        if self._speech_coordinator is not None:
            self._speech_coordinator.cancel_current()

    def _copy(self, command: CopyResult) -> None:
        controller = self._workflow_controller(command.session_id)
        if controller and controller.snapshot.content:
            text = _selected_or_result(command.text, controller)
            intent = OutputOperationIntent(command.operation_id or uuid.uuid4().hex, command.session_id, "copy", text)
            self._run_output_action(intent, lambda: self._output_actions.copy(text))

    def _paste(self, command: PasteResult) -> None:
        controller = self._workflow_controller(command.session_id)
        operation_id = command.operation_id or uuid.uuid4().hex
        if controller is None or not controller.snapshot.content:
            self._reject_paste(operation_id, command.session_id, "This result is no longer available to paste.")
            return
        if not self._output_actions.can_paste:
            self._reject_paste(operation_id, command.session_id, "Paste output is not configured.")
            return
        target = self._paste_targets.current
        if target is None:
            self._reject_paste(
                operation_id,
                command.session_id,
                "找不到貼上目標。請先點選要貼入的視窗，再回到 ClipAI。",
            )
            return
        text = _selected_or_result(command.text, controller)
        intent = OutputOperationIntent(operation_id, command.session_id, "paste", text)
        keep_workflow = controller.snapshot.pinned
        operation = self._operations.begin(intent)
        try:
            self._supervisor.submit(
                intent.operation_id,
                lambda: self._complete_paste(intent, operation, keep_workflow, target),
                lambda error: logger.error("Paste failed session_id=%s: %s", command.session_id, error),
            )
        except BaseException as exc:
            self._operations.fail(intent, exc, operation)
            logger.error("Could not schedule paste session_id=%s: %s", command.session_id, exc)

    def _reject_paste(self, operation_id: str, workflow_id: str, message: str) -> None:
        intent = OutputOperationIntent(operation_id, workflow_id, "paste", "")
        operation = self._operations.begin(intent)
        self._operations.fail(intent, RuntimeError(message), operation)

    def _archive(self, command: ArchiveResult) -> None:
        controller = self._workflow_controller(command.session_id)
        if controller and controller.snapshot.content and self._output_actions.can_archive:
            text = _selected_or_result(command.text, controller)
            intent = OutputOperationIntent(command.operation_id or uuid.uuid4().hex, command.session_id, "archive", text)
            self._run_output_action(intent, lambda: self._output_actions.archive(text))

    def _run_output_action(self, intent: OutputOperationIntent, work: Callable[[], None]) -> None:
        operation = self._operations.begin(intent)
        self._supervisor.submit(
            intent.operation_id,
            lambda: self._complete_output_action(intent, operation, work),
            lambda error: logger.error("%s failed workflow_id=%s: %s", intent.kind, intent.workflow_id, error),
        )

    def _complete_output_action(self, intent, operation, work: Callable[[], None]) -> None:
        try:
            work()
        except BaseException as exc:
            self._operations.fail(intent, exc, operation)
            raise
        self._operations.succeed(intent, operation)

    def _complete_paste(self, intent, operation, keep_workflow: bool, target: PasteTarget) -> None:
        try:
            self._output_actions.paste(intent.text, target)
        except BaseException as exc:
            self._operations.fail(intent, exc, operation)
            raise
        if not self._operations.succeed(intent, operation):
            return
        if keep_workflow:
            self._enqueue(ReleaseForegroundWorkflow(intent.workflow_id))
        else:
            self._enqueue(CloseSession(intent.workflow_id))

    def _speak_selection_or_clipboard(self) -> None:
        if self._speech_coordinator is None:
            return
        if self._cancel_current_speech_projection():
            return
        job = self._speech_coordinator.create_job(clipboard_only=self._has_foreground_workflow())
        intent = OutputOperationIntent(job.operation_id, job.workflow_id, "speech", "")
        operation = self._operations.begin(intent)
        self._supervisor.submit(
            f"speech:{job.operation_id}",
            lambda: self._run_speech_job(job, intent, operation, None),
            lambda error: self._handle_speech_error(job.operation_id, error),
        )

    def _toggle_speech(self, session_id: str, selected_text: str | None, requested_operation_id: str) -> None:
        controller = self._workflow_controller(session_id)
        if controller is None or not controller.snapshot.content or self._speech_coordinator is None:
            return
        if controller.snapshot.speaking:
            operation_id = self._speech_coordinator.operation_for(session_id)
            if operation_id is not None:
                self._speech_coordinator.cancel_operation(operation_id)
                self._supervisor.cancel(operation_id)
                self._operations.cancel(OutputOperationIntent(operation_id, session_id, "speech", ""))
            controller.set_speaking(False)
            return
        self._cancel_current_speech_projection()
        controller.set_speaking(True)
        text = selected_text.strip() if selected_text and selected_text.strip() else controller.snapshot.content
        operation_id = requested_operation_id or uuid.uuid4().hex
        intent = OutputOperationIntent(operation_id, session_id, "speech", text)
        operation = self._operations.begin(intent)
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
            current = self._operations.fail(intent, exc, operation)
            if current and controller is not None:
                controller.set_speaking(False)
            raise
        current = self._operations.succeed(intent, operation)
        if current and controller is not None:
            controller.set_speaking(False)

    def _cancel_current_speech_projection(self) -> bool:
        if self._speech_coordinator is None:
            return False
        identity = self._speech_coordinator.current_identity
        if identity is None:
            return False
        operation_id, workflow_id = identity
        if not self._speech_coordinator.cancel_operation(operation_id):
            return False
        self._supervisor.cancel(operation_id)
        self._operations.cancel(OutputOperationIntent(operation_id, workflow_id, "speech", ""))
        previous = self._workflow_controller(workflow_id)
        if previous is not None:
            previous.set_speaking(False)
        return True

    def _handle_speech_error(self, session_id: str, error: BaseException) -> None:
        self._incident_reporter.report(error, context=f"speech:{session_id}")
        controller = self._workflow_controller(session_id)
        if controller:
            controller.set_speaking(False)

    def _export_diagnostics(self) -> None:
        if self._diagnostics_exporter is None:
            if self._notifier is not None:
                self._notifier.notify("ClipAI Diagnostics", "Diagnostics export is not configured.")
            return
        diagnostics_exporter = self._diagnostics_exporter

        def export() -> None:
            destination = diagnostics_exporter.export()
            if self._notifier is not None:
                self._notifier.notify("ClipAI Diagnostics", f"Exported to {destination}")

        self._supervisor.submit("diagnostics:export", export, self._handle_diagnostics_error)

    def _handle_diagnostics_error(self, error: BaseException) -> None:
        incident_id = self._incident_reporter.report(error, context="diagnostics:export")
        if self._notifier is not None:
            self._notifier.notify("ClipAI Diagnostics", f"Export failed. Incident: {incident_id}")


def _selected_or_result(selected: str | None, controller: WorkflowController) -> str:
    return selected.strip() if selected and selected.strip() else controller.snapshot.content
