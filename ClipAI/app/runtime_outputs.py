from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TypeAlias
import logging
import uuid

from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.commands import ArchiveResult, CopyResult, ExportDiagnostics, PasteOperationCompleted, PasteResult, SpeakSelectionOrClipboard, ToggleSpeech
from ClipAI.core.errors import PASTE_FAILURE_MESSAGES, PasteFailure
from ClipAI.core.models import OutputOperationIntent, OutputOperationResult, PasteOutcome, PasteRequest, PasteTarget
from ClipAI.core.ports import DiagnosticsExporter, OperationTracker, OutputOperationPresenter, UserNotifier
from ClipAI.services.output_actions import OutputActions
from ClipAI.services.output_operation import OutputOperationCoordinator, paste_outcome_result
from ClipAI.services.paste_target import PasteTargetCoordinator
from ClipAI.services.paste_operation import PasteOperationCoordinator
from ClipAI.services.speech_coordinator import SpeechCoordinator
from ClipAI.services.workflow_controller import WorkflowController
from ClipAI.services.user_control import UserControlCoordinator
from ClipAI.support.diagnostics import IncidentReporter

logger = logging.getLogger("clipai.runtime.outputs")

ResultOutputRuntimeCommand: TypeAlias = CopyResult | PasteResult | PasteOperationCompleted | ArchiveResult | ToggleSpeech | SpeakSelectionOrClipboard | ExportDiagnostics


class ResultOutputRuntimeModule:
    """Owns output-operation scheduling, identity, and user-visible completion."""

    def __init__(
        self,
        *,
        output_actions: OutputActions,
        paste_operations: PasteOperationCoordinator,
        supervisor: TaskSupervisor,
        workflow_controller: Callable[[str], WorkflowController | None],
        output_operation_presenter: OutputOperationPresenter,
        incident_reporter: IncidentReporter,
        operation_tracker: OperationTracker | None = None,
        diagnostics_exporter: DiagnosticsExporter | None = None,
        notifier: UserNotifier | None = None,
        speech_coordinator: SpeechCoordinator | None = None,
        paste_targets: PasteTargetCoordinator | None = None,
        user_control: UserControlCoordinator | None = None,
    ) -> None:
        self._output_actions = output_actions
        self._paste_operations = paste_operations
        self._supervisor = supervisor
        self._workflow_controller = workflow_controller
        self._incident_reporter = incident_reporter
        self._operation_tracker = operation_tracker
        self._diagnostics_exporter = diagnostics_exporter
        self._notifier = notifier
        self._speech_coordinator = speech_coordinator
        self._paste_targets = paste_targets or PasteTargetCoordinator()
        self._operations = OutputOperationCoordinator(output_operation_presenter, operation_tracker)
        self._user_control = user_control

    def observe_paste_target(self, target: PasteTarget) -> None:
        self._paste_targets.observe(target)

    @property
    def current_paste_target(self) -> PasteTarget | None:
        """Expose the latest external foreground target for capture-time freezing."""
        return self._paste_targets.current

    def bind_user_control(self, user_control: UserControlCoordinator) -> None:
        self._user_control = user_control
        self._operations.bind_user_control(user_control)

    def handle(self, command: ResultOutputRuntimeCommand) -> None:
        if isinstance(command, CopyResult):
            self._copy(command)
        elif isinstance(command, PasteResult):
            self._paste(command)
        elif isinstance(command, PasteOperationCompleted):
            self._paste_completed(command)
        elif isinstance(command, ArchiveResult):
            self._archive(command)
        elif isinstance(command, ToggleSpeech):
            self._toggle_speech(command.session_id, command.text, command.operation_id)
        elif isinstance(command, SpeakSelectionOrClipboard):
            self._speak_selection_or_clipboard()
        elif isinstance(command, ExportDiagnostics):
            self._export_diagnostics()

    def close_workflow(self, workflow_id: str) -> None:
        paste_operation_id = self._paste_operations.request_cancel_for_workflow(workflow_id)
        if paste_operation_id is not None:
            self._supervisor.cancel_many((paste_operation_id,), lambda: None)
        if self._speech_coordinator is None:
            return
        operation_id = self._speech_coordinator.operation_for(workflow_id)
        if operation_id is None:
            return
        self._speech_coordinator.cancel_operation(operation_id)
        self._supervisor.cancel(operation_id)
        self._operations.settle(OutputOperationResult(operation_id, workflow_id, "speech", "cancelled"))

    def stop(self) -> None:
        paste_operation_id = self._paste_operations.request_cancel_active()
        if paste_operation_id is not None:
            self._supervisor.cancel_many((paste_operation_id,), lambda: None)
        if self._speech_coordinator is not None:
            self._speech_coordinator.cancel_current()

    def cancel_active_operations(self) -> tuple[str, ...]:
        speech_identity = self._speech_coordinator.current_identity if self._speech_coordinator is not None else None
        if self._speech_coordinator is not None:
            self._speech_coordinator.cancel_current()
        task_ids: list[str] = []
        paste_operation_id = self._paste_operations.request_cancel_active()
        if paste_operation_id is not None:
            task_ids.append(paste_operation_id)
        intents = self._operations.cancel_all(
            exclude_operation_ids=(
                frozenset({paste_operation_id})
                if paste_operation_id is not None
                else frozenset()
            )
        )
        for intent in intents:
            task_ids.append(intent.operation_id)
            if intent.kind == "speech":
                task_ids.append(f"speech:{intent.operation_id}")
                controller = self._workflow_controller(intent.workflow_id)
                if controller is not None and controller.snapshot.speaking:
                    controller.set_speaking(False)
        if speech_identity is not None and all(intent.operation_id != speech_identity[0] for intent in intents):
            task_ids.extend((speech_identity[0], f"speech:{speech_identity[0]}"))
            controller = self._workflow_controller(speech_identity[1])
            if controller is not None and controller.snapshot.speaking:
                controller.set_speaking(False)
        return tuple(dict.fromkeys(task_ids))

    def cancel_operation(self, operation_id: str) -> tuple[str, ...]:
        if self._paste_operations.request_cancel(operation_id):
            self._supervisor.cancel_many((operation_id,), lambda: None)
            return (operation_id,)
        identity = self._speech_coordinator.current_identity if self._speech_coordinator is not None else None
        if identity is not None and identity[0] == operation_id:
            self._speech_coordinator.cancel_operation(operation_id)
        intent = self._operations.cancel_operation(operation_id)
        if intent is None and (identity is None or identity[0] != operation_id):
            return ()
        workflow_id = intent.workflow_id if intent is not None else identity[1]
        controller = self._workflow_controller(workflow_id)
        if controller is not None and controller.snapshot.speaking:
            controller.set_speaking(False)
        task_ids = [operation_id]
        if (intent is not None and intent.kind == "speech") or (identity is not None and identity[0] == operation_id):
            task_ids.append(f"speech:{operation_id}")
        self._supervisor.cancel_many(task_ids, lambda: None)
        return tuple(task_ids)

    def cancel_all_content_operations(self) -> tuple[str, ...]:
        return self.cancel_active_operations()

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
            self._reject_paste(
                operation_id,
                command.session_id,
                "",
                PasteFailure("unknown", PASTE_FAILURE_MESSAGES["unknown"]),
            )
            return
        text = _selected_or_result(command.text, controller)
        voice_origin = controller.snapshot.voice_origin
        target = (
            voice_origin.paste_target
            if voice_origin is not None and voice_origin.paste_target is not None
            else self._paste_targets.current
        )
        if target is None:
            self._reject_paste(
                operation_id,
                command.session_id,
                text,
                PasteFailure(
                    "no_target_observed",
                    PASTE_FAILURE_MESSAGES["no_target_observed"],
                ),
            )
            return
        intent = OutputOperationIntent(operation_id, command.session_id, "paste", text)
        try:
            self._operations.begin(intent)
        except BaseException as exc:
            logger.error("Could not begin paste session_id=%s: %s", command.session_id, exc)
            return
        try:
            admitted = self._paste_operations.admit(
                PasteRequest(operation_id, command.session_id, text, target)
            )
        except BaseException as exc:
            self._operations.fail(intent, exc)
            logger.error("Could not admit paste session_id=%s: %s", command.session_id, exc)
            return
        if not admitted:
            logger.warning("Ignored overlapping Paste Operation workflow_id=%s", command.session_id)
            return
        try:
            self._supervisor.submit(
                intent.operation_id,
                lambda: self._paste_operations.execute(intent.operation_id),
                lambda error: logger.error("Paste failed session_id=%s: %s", command.session_id, error),
                task_class="interactive",
                cancellation_hook=lambda: self._paste_operations.request_cancel(intent.operation_id),
            )
        except BaseException as exc:
            self._paste_operations.fail_to_start(intent.operation_id, exc)
            logger.error("Could not schedule paste session_id=%s: %s", command.session_id, exc)

    def _reject_paste(
        self,
        operation_id: str,
        workflow_id: str,
        text: str,
        failure: PasteFailure,
    ) -> None:
        intent = OutputOperationIntent(operation_id, workflow_id, "paste", text)
        try:
            self._operations.begin(intent)
            result = paste_outcome_result(
                intent,
                PasteOutcome(
                    "failed",
                    "not_dispatched",
                    "not_required",
                    str(failure),
                    failure.reason,
                ),
            )
            preserved = self._preserve_failed_paste_content(intent, result)
            if preserved is not None:
                self._operations.settle(preserved)
        except BaseException as exc:
            logger.error("Could not reject paste workflow_id=%s: %s", workflow_id, exc)

    def _archive(self, command: ArchiveResult) -> None:
        controller = self._workflow_controller(command.session_id)
        if controller and controller.snapshot.content and self._output_actions.can_archive:
            text = _selected_or_result(command.text, controller)
            intent = OutputOperationIntent(command.operation_id or uuid.uuid4().hex, command.session_id, "archive", text)
            self._run_output_action(intent, lambda: self._output_actions.archive(text))

    def _run_output_action(self, intent: OutputOperationIntent, work: Callable[[], None]) -> None:
        self._begin_and_submit(intent, work, task_class="interactive")

    def _complete_output_action(self, intent, work: Callable[[], None]) -> None:
        try:
            work()
        except BaseException as exc:
            self._operations.fail(intent, exc)
            raise
        self._operations.settle(OutputOperationResult(
            intent.operation_id, intent.workflow_id, intent.kind, "succeeded"
        ))

    def _paste_completed(self, command: PasteOperationCompleted) -> None:
        intent = self._operations.active_intent(
            command.operation_id,
            command.workflow_id,
            "paste",
        )
        if intent is None:
            return
        result = paste_outcome_result(intent, command.outcome)
        if result.state in {"failed", "cancelled"}:
            preserved = self._preserve_failed_paste_content(intent, result)
            if preserved is None:
                return
            result = preserved
        self._operations.settle(result)

    def _preserve_failed_paste_content(
        self,
        intent: OutputOperationIntent,
        result: OutputOperationResult,
    ) -> OutputOperationResult | None:
        if not intent.text:
            return result
        try:
            self._output_actions.copy(intent.text)
        except BaseException:
            failure = PasteFailure(
                "clipboard_unavailable",
                PASTE_FAILURE_MESSAGES["clipboard_unavailable"],
            )
            self._operations.fail(intent, failure)
            return None
        fallback = "結果已保留在剪貼簿，可切回目標視窗自行按 Ctrl+V。"
        if result.error is not None:
            return replace(
                result,
                error=replace(result.error, message=f"{result.error.message} {fallback}"),
            )
        return replace(result, message=f"{result.message or '貼上已取消。'} {fallback}")

    def _speak_selection_or_clipboard(self) -> None:
        if self._speech_coordinator is None:
            return
        replacing = self._cancel_current_speech_projection()
        job = self._speech_coordinator.create_job(clipboard_only=False)
        if replacing and self._notifier is not None:
            preview = " ".join(getattr(job, "text", "").split())
            if len(preview) > 36:
                preview = f"{preview[:35]}…"
            self._notifier.notify("ClipAI", f"正在切換到：{preview}" if preview else "正在切換朗讀內容…")
        intent = OutputOperationIntent(job.operation_id, job.workflow_id, "speech", "")
        self._begin_and_submit(
            intent,
            lambda: self._run_speech_job(job, intent, None),
            task_class="media",
            task_id=f"speech:{job.operation_id}",
            on_error=lambda error: self._handle_speech_error(job.operation_id, error),
            cancellation_hook=lambda: self._speech_coordinator.cancel_operation(job.operation_id),
            settles_itself=True,
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
                self._operations.settle(OutputOperationResult(operation_id, session_id, "speech", "cancelled"))
            controller.set_speaking(False)
            return
        self._cancel_current_speech_projection()
        controller.set_speaking(True)
        text = selected_text.strip() if selected_text and selected_text.strip() else controller.snapshot.content
        operation_id = requested_operation_id or uuid.uuid4().hex
        intent = OutputOperationIntent(operation_id, session_id, "speech", text)
        job = self._speech_coordinator.create_text_job(operation_id=operation_id, workflow_id=session_id, text=text)
        self._begin_and_submit(
            intent,
            lambda: self._run_speech_job(job, intent, controller),
            task_class="media",
            on_error=lambda error: self._handle_speech_error(session_id, error),
            cancellation_hook=lambda: self._speech_coordinator.cancel_operation(operation_id),
            settles_itself=True,
        )

    def _run_speech_job(self, job, intent, controller) -> None:
        try:
            job.run()
        except BaseException as exc:
            current = self._operations.fail(intent, exc)
            if current and controller is not None:
                controller.set_speaking(False)
            raise
        current = self._operations.settle(OutputOperationResult(
            intent.operation_id, intent.workflow_id, intent.kind, "succeeded"
        ))
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
        self._operations.settle(OutputOperationResult(operation_id, workflow_id, "speech", "cancelled"))
        previous = self._workflow_controller(workflow_id)
        if previous is not None:
            previous.set_speaking(False)
        return True

    def _begin_and_submit(
        self,
        intent: OutputOperationIntent,
        work: Callable[[], None],
        *,
        task_class: str,
        task_id: str | None = None,
        on_error: Callable[[BaseException], None] | None = None,
        cancellation_hook: Callable[[], None] | None = None,
        settles_itself: bool = False,
    ) -> None:
        try:
            self._operations.begin(intent)
            self._supervisor.submit(
                task_id or intent.operation_id,
                work if settles_itself else lambda: self._complete_output_action(intent, work),
                on_error or (lambda error: logger.error("%s failed workflow_id=%s: %s", intent.kind, intent.workflow_id, error)),
                task_class=task_class,
                cancellation_hook=cancellation_hook,
            )
        except BaseException as exc:
            self._operations.fail(intent, exc)
            logger.error("Could not schedule %s workflow_id=%s: %s", intent.kind, intent.workflow_id, exc)

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

        self._supervisor.submit(
            "diagnostics:export",
            export,
            self._handle_diagnostics_error,
            task_class="maintenance",
        )

    def _handle_diagnostics_error(self, error: BaseException) -> None:
        incident_id = self._incident_reporter.report(error, context="diagnostics:export")
        if self._notifier is not None:
            self._notifier.notify("ClipAI Diagnostics", f"Export failed. Incident: {incident_id}")


def _selected_or_result(selected: str | None, controller: WorkflowController) -> str:
    return selected.strip() if selected is not None else controller.snapshot.content
