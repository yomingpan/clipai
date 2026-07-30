from __future__ import annotations

from collections.abc import Callable
from typing import cast
import queue
import uuid

from ClipAI.app.runtime_outputs import ResultOutputRuntimeCommand, ResultOutputRuntimeModule
from ClipAI.app.runtime_provider_configuration import ProviderConfigurationRuntimeModule, ProviderRuntimeCommand
from ClipAI.app.runtime_shortcut_guide import ShortcutGuideRuntimeCommand, ShortcutGuideRuntimeModule
from ClipAI.app.runtime_user_persistence import UserPersistenceRuntimeCommand, UserPersistenceRuntimeModule
from ClipAI.app.runtime_workflows import HeadlessWorkflowFinished, WorkflowInvocationFailed, WorkflowRuntimeCommand, WorkflowRuntimeModule
from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.commands import ActionFeedbackCompleted, ActivateWorkflow, ActiveOperationsCancelled, ArchiveResult, CancelActiveOperations, CancelSession, CloseSession, CloseShortcutGuide, CopyResult, ExportDiagnostics, ExternalForegroundChanged, FollowUp, GuidancePreferencesCompleted, NavigateWorkflowBack, OpenProviderSettings, OpenShortcutGuide, PasteResult, RefreshProviderModels, ReleaseForegroundWorkflow, ReloadConfiguration, ResetFirstUseHints, SelectProvider, SelectProviderModel, SelectShortcutGuideItem, SetFirstUseHintsEnabled, ShortcutGestureProgressed, ShortcutTriggered, ShutdownApplication, SpeakSelectionOrClipboard, StartAction, SubmitActionFeedback, TogglePin, ToggleSpeech, ValidateAndSaveProviderSettings
from ClipAI.core.models import HotkeyEventType
from ClipAI.core.ports import ApplicationView, ForegroundWindowMonitor, OperationTracker, RuntimeComponent, Stoppable, UserNotifier
from ClipAI.services.provider_configuration import ProviderConfigurationResult
from ClipAI.services.shortcut_catalog import ShortcutCatalog


_WORKFLOW_COMMANDS = (StartAction, CloseSession, CancelSession, TogglePin, FollowUp, ActivateWorkflow, ReleaseForegroundWorkflow, NavigateWorkflowBack, WorkflowInvocationFailed, HeadlessWorkflowFinished)
_OUTPUT_COMMANDS = (CopyResult, PasteResult, ArchiveResult, ToggleSpeech, SpeakSelectionOrClipboard, ExportDiagnostics)
_PROVIDER_COMMANDS = (SelectProviderModel, SelectProvider, ReloadConfiguration, OpenProviderSettings, ValidateAndSaveProviderSettings, RefreshProviderModels, ProviderConfigurationResult)
_USER_PERSISTENCE_COMMANDS = (SubmitActionFeedback, ActionFeedbackCompleted, SetFirstUseHintsEnabled, ResetFirstUseHints, GuidancePreferencesCompleted)
_SHORTCUT_GUIDE_COMMANDS = (OpenShortcutGuide, CloseShortcutGuide, SelectShortcutGuideItem, ShortcutGestureProgressed)


class AppRuntime:
    """Owns the command queue and desktop runtime lifecycle; modules own command policy."""

    def __init__(
        self,
        *,
        shortcuts: ShortcutCatalog,
        view: ApplicationView,
        supervisor: TaskSupervisor,
        workflows: WorkflowRuntimeModule,
        result_output: ResultOutputRuntimeModule,
        provider_configuration: ProviderConfigurationRuntimeModule,
        user_persistence: UserPersistenceRuntimeModule,
        hotkey_registrar: Callable[
            [
                dict[str, dict[str, str]],
                Callable[[str, HotkeyEventType, int], None],
                Callable[[int, frozenset[str], bool], None],
            ],
            Stoppable,
        ],
        tray_factory: Callable[[Callable[[], None]], RuntimeComponent] | None = None,
        operation_tracker: OperationTracker | None = None,
        shortcut_guide: ShortcutGuideRuntimeModule | None = None,
        foreground_monitor: ForegroundWindowMonitor | None = None,
        notifier: UserNotifier | None = None,
    ) -> None:
        self._shortcuts = shortcuts
        self._view = view
        self._supervisor = supervisor
        self._workflow_module = workflows
        self._result_output_module = result_output
        self._provider_configuration_module = provider_configuration
        self._user_persistence_module = user_persistence
        self._hotkey_registrar = hotkey_registrar
        self._tray_factory = tray_factory
        self._operation_tracker = operation_tracker
        self._shortcut_guide_module = shortcut_guide
        self._foreground_monitor = foreground_monitor
        self._notifier = notifier
        self._active_cancellation_id: str | None = None
        self._commands: queue.Queue[object] = queue.Queue()
        self._listener: Stoppable | None = None
        self._tray: RuntimeComponent | None = None
        self._stopping = False
        self._view.set_command_sink(self.enqueue)

        # Provider configuration compatibility probes remain until that module's
        # tests migrate to constructor-injected presenters.
        self._provider_configuration = provider_configuration.coordinator

    @property
    def _model_selection_presenter(self):
        return self._provider_configuration_module._model_selection_presenter

    @_model_selection_presenter.setter
    def _model_selection_presenter(self, presenter) -> None:
        self._provider_configuration_module._model_selection_presenter = presenter

    @property
    def _provider_selection_presenter(self):
        return self._provider_configuration_module._provider_selection_presenter

    @_provider_selection_presenter.setter
    def _provider_selection_presenter(self, presenter) -> None:
        self._provider_configuration_module._provider_selection_presenter = presenter

    def enqueue(self, command: object) -> None:
        if not self._stopping:
            self._commands.put(command)

    def start(self) -> None:
        if self._foreground_monitor is not None:
            self._foreground_monitor.start()
        self._listener = self._hotkey_registrar(
            self._shortcuts.hotkey_map(),
            lambda shortcut_id, press_type, gesture_id: self.enqueue(ShortcutTriggered(shortcut_id, press_type, gesture_id)),
            self._enqueue_shortcut_progress,
        )
        if self._tray_factory is not None:
            self._tray = self._tray_factory(lambda: self.enqueue(ShutdownApplication()))
            self._tray.start()

    def _enqueue_shortcut_progress(self, gesture_id: int, pressed_keys: frozenset[str], ended: bool) -> None:
        guide = self._shortcut_guide_module
        if guide is not None and guide.wants_progress(gesture_id):
            self.enqueue(ShortcutGestureProgressed(gesture_id, pressed_keys, ended))

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
            self._route(command)

    def stop(self) -> None:
        if self._stopping:
            return
        self._stopping = True
        if self._foreground_monitor is not None:
            self._foreground_monitor.stop()
        self._workflow_module.stop()
        self._result_output_module.stop()
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

    def show_last_error(self) -> None:
        self._workflow_module.show_last_error()

    def _route(self, command: object) -> None:
        if isinstance(command, ShortcutTriggered):
            if command.press_type == "cancel":
                if self._shortcut_guide_module is not None and self._shortcut_guide_module.consume(command):
                    return
                self._route(CancelActiveOperations())
                return
            if self._shortcut_guide_module is not None and self._shortcut_guide_module.consume(command):
                return
            resolved = self._workflow_module.resolve_shortcut(command)
            if resolved is not None:
                self._route(resolved)
        elif isinstance(command, ExternalForegroundChanged):
            self._result_output_module.observe_paste_target(command.target)
        elif isinstance(command, _SHORTCUT_GUIDE_COMMANDS):
            if self._shortcut_guide_module is not None:
                if isinstance(command, OpenShortcutGuide):
                    self._workflow_module.cancel_shortcut_sequence()
                self._shortcut_guide_module.handle(cast(ShortcutGuideRuntimeCommand, command))
        elif isinstance(command, ShutdownApplication):
            self.stop()
        elif isinstance(command, CancelActiveOperations):
            self._cancel_active_operations(command)
        elif isinstance(command, ActiveOperationsCancelled):
            self._complete_active_operations_cancellation(command)
        elif isinstance(command, CloseSession):
            self._result_output_module.close_workflow(command.session_id)
            self._workflow_module.handle(command)
        elif isinstance(command, _WORKFLOW_COMMANDS):
            self._workflow_module.handle(cast(WorkflowRuntimeCommand, command))
        elif isinstance(command, _OUTPUT_COMMANDS):
            self._result_output_module.handle(cast(ResultOutputRuntimeCommand, command))
        elif isinstance(command, _PROVIDER_COMMANDS):
            self._provider_configuration_module.handle(cast(ProviderRuntimeCommand, command))
        elif isinstance(command, _USER_PERSISTENCE_COMMANDS):
            self._user_persistence_module.handle(cast(UserPersistenceRuntimeCommand, command))

    def _cancel_active_operations(self, command: CancelActiveOperations) -> None:
        task_ids = (
            *self._workflow_module.cancel_active_operations(),
            *self._result_output_module.cancel_active_operations(),
        )
        if not task_ids:
            return
        operation_id = command.operation_id or uuid.uuid4().hex
        self._active_cancellation_id = operation_id
        if self._notifier is not None:
            self._notifier.notify("ClipAI", "正在停止所有 ClipAI 操作…")
        self._supervisor.cancel_many(
            task_ids,
            lambda: self.enqueue(ActiveOperationsCancelled(operation_id)),
        )

    def _complete_active_operations_cancellation(self, command: ActiveOperationsCancelled) -> None:
        if command.operation_id != self._active_cancellation_id:
            return
        self._active_cancellation_id = None
        if self._notifier is not None:
            self._notifier.notify("ClipAI", "已停止所有 ClipAI 操作")
