from __future__ import annotations

from collections.abc import Callable
import logging
import queue
import uuid

from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.commands import AppCommand, ArchiveResult, CancelSession, CloseSession, CopyResult, ExportDiagnostics, FollowUp, PasteResult, ShutdownApplication, SpeakSelectionOrClipboard, StartAction, TogglePin, ToggleSpeech
from ClipAI.core.ports import ApplicationView, DiagnosticsExporter, OperationHandle, OperationTracker, UserNotifier
from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.services.action_catalog import ActionCatalog
from ClipAI.services.execute_action import ExecuteAction
from ClipAI.services.output_actions import OutputActions
from ClipAI.services.session_controller import SessionController
from ClipAI.services.shortcut_catalog import ShortcutCatalog
from ClipAI.services.speech_coordinator import SpeechCoordinator
from ClipAI.support.diagnostics import IncidentReporter

logger = logging.getLogger("clipai.runtime")


class AppRuntime:
    def __init__(
        self,
        *,
        actions: ActionCatalog,
        shortcuts: ShortcutCatalog,
        execute_action: ExecuteAction,
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
        self._commands: queue.Queue[AppCommand] = queue.Queue()
        self._sessions: dict[str, SessionController] = {}
        self._session_actions: dict[str, object] = {}
        self._speech_operations: dict[str, OperationHandle] = {}
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
            lambda shortcut_id, press_type: self.enqueue(self._shortcuts.resolve(shortcut_id, press_type)),
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
        for controller in list(self._sessions.values()):
            controller.cancel()
        for operation in list(self._speech_operations.values()):
            operation.cancel()
        self._speech_operations.clear()
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
        if isinstance(command, StartAction):
            self._start_action(command)
        elif isinstance(command, CloseSession):
            self._close(command.session_id)
        elif isinstance(command, CancelSession):
            self._cancel(command.session_id)
        elif isinstance(command, CopyResult):
            controller = self._sessions.get(command.session_id)
            if controller and controller.snapshot.content:
                self._output_actions.copy(command.text.strip() if command.text and command.text.strip() else controller.snapshot.content)
        elif isinstance(command, PasteResult):
            controller = self._sessions.get(command.session_id)
            if controller and controller.snapshot.content and self._output_actions.can_paste:
                text = command.text.strip() if command.text and command.text.strip() else controller.snapshot.content
                self._close(command.session_id)
                self._supervisor.submit(
                    f"paste:{command.session_id}",
                    lambda: self._output_actions.paste(text),
                    lambda error: logger.exception("Paste failed session_id=%s", command.session_id, exc_info=error),
                )
        elif isinstance(command, ArchiveResult):
            controller = self._sessions.get(command.session_id)
            if controller and controller.snapshot.content and self._output_actions.can_archive:
                self._output_actions.archive(controller.snapshot.content)
        elif isinstance(command, TogglePin):
            controller = self._sessions.get(command.session_id)
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

    def _speak_selection_or_clipboard(self) -> None:
        if self._speech_coordinator is None:
            return
        job = self._speech_coordinator.create_job(clipboard_only=self._has_active_sessions())
        self._supervisor.submit(
            f"speech:{job.operation_id}",
            job.run,
            lambda error: self._handle_speech_error(job.operation_id, error),
        )

    def _has_active_sessions(self) -> bool:
        return bool(self._sessions)

    def _start_action(self, command: StartAction) -> None:
        previous = self._sessions.get(self._foreground_id or "")
        if previous is not None and not previous.snapshot.pinned:
            previous.cancel()
            self._supervisor.cancel(previous.snapshot.session_id)
        action = self._actions.resolve(command.action_id, command.press_type)
        session_id = uuid.uuid4().hex
        controller = SessionController(
            SessionSnapshot(
                session_id=session_id,
                revision=0,
                status=SessionStatus.CREATED,
                action_id=action.id,
                title=action.name,
                model=self._model,
            ),
            self._view,
        )
        self._sessions[session_id] = controller
        self._session_actions[session_id] = action
        self._foreground_id = session_id
        self._supervisor.submit(
            session_id,
            lambda: self._execute_action.execute(action, controller),
            lambda error: self._handle_unhandled(session_id, error),
        )

    def _follow_up(self, command: FollowUp) -> None:
        controller = self._sessions.get(command.session_id)
        action = self._session_actions.get(command.session_id)
        if controller is None or action is None or not command.text.strip():
            return
        self._supervisor.submit(
            command.session_id,
            lambda: self._execute_action.execute_follow_up(action, command.text, controller),  # type: ignore[arg-type]
            lambda error: self._handle_unhandled(command.session_id, error),
        )

    def _cancel(self, session_id: str) -> None:
        controller = self._sessions.get(session_id)
        if controller:
            controller.cancel()
            self._supervisor.cancel(session_id)

    def _toggle_speech(self, session_id: str, selected_text: str | None = None) -> None:
        controller = self._sessions.get(session_id)
        if controller is None or not controller.snapshot.content or not self._output_actions.can_speak:
            return
        if controller.snapshot.speaking:
            self._output_actions.stop_speech()
            controller.set_speaking(False)
            operation = self._speech_operations.pop(session_id, None)
            if operation is not None:
                operation.cancel()
            return
        if self._speech_coordinator is not None:
            self._speech_coordinator.cancel_current()
        controller.set_speaking(True)
        text = selected_text.strip() if selected_text and selected_text.strip() else controller.snapshot.content
        operation = self._operation_tracker.start(f"tts:{session_id}", "tts") if self._operation_tracker else None
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
                self._speech_operations.pop(session_id, None)
                controller.set_speaking(False)

        self._supervisor.submit(
            f"speech:{session_id}",
            speak,
            lambda error: self._handle_speech_error(session_id, error),
        )

    def _close(self, session_id: str) -> None:
        controller = self._sessions.pop(session_id, None)
        self._session_actions.pop(session_id, None)
        if controller:
            self._output_actions.stop_speech()
            operation = self._speech_operations.pop(session_id, None)
            if operation is not None:
                operation.cancel()
            controller.close()
            self._supervisor.cancel(session_id)
        if self._foreground_id == session_id:
            self._foreground_id = None

    def _handle_unhandled(self, session_id: str, error: BaseException) -> None:
        incident_id = self._incident_reporter.report(error, context=f"session:{session_id}")
        controller = self._sessions.get(session_id)
        if controller:
            controller.fail(f"ClipAI encountered an unexpected error. Incident: {incident_id}")

    def _handle_speech_error(self, session_id: str, error: BaseException) -> None:
        self._incident_reporter.report(error, context=f"speech:{session_id}")
        controller = self._sessions.get(session_id)
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
