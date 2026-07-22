from __future__ import annotations

from collections.abc import Callable
from typing import cast
import queue

from ClipAI.app.runtime_outputs import ResultOutputRuntimeCommand, ResultOutputRuntimeModule
from ClipAI.app.runtime_provider_configuration import ProviderConfigurationRuntimeModule, ProviderRuntimeCommand
from ClipAI.app.runtime_user_persistence import UserPersistenceRuntimeCommand, UserPersistenceRuntimeModule
from ClipAI.app.runtime_workflows import WorkflowRuntimeCommand, WorkflowRuntimeModule
from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.commands import ActionFeedbackCompleted, ActivateWorkflow, ArchiveResult, CancelSession, CloseSession, CopyResult, ExportDiagnostics, FollowUp, GuidancePreferencesCompleted, NavigateWorkflowBack, OpenProviderSettings, PasteResult, RefreshProviderModels, ReloadConfiguration, ResetFirstUseHints, SelectProvider, SelectProviderModel, SetFirstUseHintsEnabled, ShortcutTriggered, ShutdownApplication, SpeakSelectionOrClipboard, StartAction, SubmitActionFeedback, TogglePin, ToggleSpeech, ValidateAndSaveProviderSettings
from ClipAI.core.models import HotkeyEventType
from ClipAI.core.ports import ApplicationView, OperationTracker, RuntimeComponent, Stoppable
from ClipAI.services.provider_configuration import ProviderConfigurationResult
from ClipAI.services.shortcut_catalog import ShortcutCatalog


_WORKFLOW_COMMANDS = (StartAction, CloseSession, CancelSession, TogglePin, FollowUp, ActivateWorkflow, NavigateWorkflowBack)
_OUTPUT_COMMANDS = (CopyResult, PasteResult, ArchiveResult, ToggleSpeech, SpeakSelectionOrClipboard, ExportDiagnostics)
_PROVIDER_COMMANDS = (SelectProviderModel, SelectProvider, ReloadConfiguration, OpenProviderSettings, ValidateAndSaveProviderSettings, RefreshProviderModels, ProviderConfigurationResult)
_USER_PERSISTENCE_COMMANDS = (SubmitActionFeedback, ActionFeedbackCompleted, SetFirstUseHintsEnabled, ResetFirstUseHints, GuidancePreferencesCompleted)


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
        hotkey_registrar: Callable[[dict[str, dict[str, str]], Callable[[str, HotkeyEventType], None]], Stoppable],
        tray_factory: Callable[[Callable[[], None]], RuntimeComponent] | None = None,
        operation_tracker: OperationTracker | None = None,
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
        self._commands: queue.Queue[object] = queue.Queue()
        self._listener: Stoppable | None = None
        self._tray: RuntimeComponent | None = None
        self._stopping = False
        self._view.set_command_sink(self.enqueue)

        # Transitional read-only test probes. Lifecycle ownership remains in the modules.
        self._workflows = workflows.workflows
        self._actions = workflows._actions
        self._execute_action = workflows._execute_action
        self._provider_configuration = provider_configuration.coordinator
        self._speech_coordinator = result_output._speech_coordinator

    @property
    def _foreground_id(self) -> str | None:
        return self._workflow_module.foreground_id

    @property
    def _sequence_workflow_id(self) -> str | None:
        return self._workflow_module.sequence_id

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
            self._route(command)

    def stop(self) -> None:
        if self._stopping:
            return
        self._stopping = True
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
            resolved = self._workflow_module.resolve_shortcut(command)
            if resolved is not None:
                self._route(resolved)
        elif isinstance(command, ShutdownApplication):
            self.stop()
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
