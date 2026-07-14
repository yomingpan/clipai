from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
import queue
import uuid

from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.errors import ConfigError
from ClipAI.core.commands import ActivateWorkflow, AppCommand, ArchiveResult, CancelSession, CloseSession, CopyResult, ExportDiagnostics, FollowUp, NavigateWorkflowBack, OpenProviderSettings, PasteResult, RefreshProviderModels, ReloadConfiguration, SelectProvider, SelectProviderModel, ShortcutTriggered, ShutdownApplication, SpeakSelectionOrClipboard, StartAction, TogglePin, ToggleSpeech, ValidateAndSaveProviderSettings
from ClipAI.core.models import ActionInvocation, EnvironmentSetting, InputDocument, InputTarget, ModelSelectionState, OutputOperationIntent, ProviderOption, ProviderSelectionState, ProviderSettingsState
from ClipAI.core.ports import ActiveWorkflowContextReader, ApplicationView, DiagnosticsExporter, EnvironmentSettingsStore, ModelSelectionPresenter, OperationTracker, OutputOperationPresenter, ProviderSelectionPresenter, ProviderSettingsPresenter, RuntimeComponent, Stoppable, UserNotifier
from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.services.action_catalog import ActionCatalog
from ClipAI.services.execute_action import ActionExecutor
from ClipAI.services.output_actions import OutputActions
from ClipAI.services.provider_binding import ProviderExecutionBinding, ProviderRuntimeSnapshot
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


@dataclass(frozen=True)
class _ProviderSettingsSaved:
    operation_id: str
    snapshot: ProviderRuntimeSnapshot


@dataclass(frozen=True)
class _ProviderSettingsFailed:
    operation_id: str
    message: str


@dataclass(frozen=True)
class _ProviderModelsRefreshed:
    operation_id: str
    provider: str
    models: tuple[str, ...]


@dataclass(frozen=True)
class _ProviderModelsRefreshFailed:
    operation_id: str
    provider: str
    message: str


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
        settings_store: EnvironmentSettingsStore | None = None,
        model_selection_presenter: ModelSelectionPresenter | None = None,
        provider_options: tuple[ProviderOption, ...] = (),
        provider_bindings: tuple[ProviderExecutionBinding, ...] = (),
        provider_selection_presenter: ProviderSelectionPresenter | None = None,
        reload_provider_settings: Callable[[], ProviderRuntimeSnapshot] | None = None,
        provider_settings_presenter: ProviderSettingsPresenter | None = None,
        validate_provider_credential: Callable[[str, str, str, str], None] | None = None,
        build_provider_candidate: Callable[[str, str, str, str, str], ProviderRuntimeSnapshot] | None = None,
        gateway_name: str = "",
        gateway_base_url: str = "",
        discover_provider_models: Callable[[str], tuple[str, ...]] | None = None,
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
        self._settings_store = settings_store
        self._model_selection_presenter = model_selection_presenter
        self._provider_options = provider_options or (
            ProviderOption(provider_binding.provider_id, provider_binding.provider_id.title(), self._available_models, provider_binding.model, not provider_binding.readiness_issues),
        )
        active_option = next((item for item in self._provider_options if item.provider_id == self._provider_name), None)
        self._custom_models = active_option.custom_models if active_option is not None else ()
        self._provider_selection_presenter = provider_selection_presenter
        self._provider_bindings = {item.provider_id: item for item in (provider_bindings or (provider_binding,))}
        self._reload_provider_settings = reload_provider_settings
        self._provider_settings_presenter = provider_settings_presenter
        self._validate_provider_credential = validate_provider_credential
        self._build_provider_candidate = build_provider_candidate
        self._gateway_name = gateway_name
        self._gateway_base_url = gateway_base_url
        self._provider_settings_operation_id = ""
        self._discover_provider_models = discover_provider_models
        self._model_refresh_operation_id = ""
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
        elif isinstance(command, SelectProvider):
            self._select_provider(command)
        elif isinstance(command, ReloadConfiguration):
            self._reload_configuration()
        elif isinstance(command, OpenProviderSettings):
            self._open_provider_settings(command.provider)
        elif isinstance(command, ValidateAndSaveProviderSettings):
            self._validate_and_save_provider_settings(command)
        elif isinstance(command, _ProviderSettingsSaved):
            self._provider_settings_saved(command)
        elif isinstance(command, _ProviderSettingsFailed):
            self._provider_settings_failed(command)
        elif isinstance(command, RefreshProviderModels):
            self._refresh_provider_models(command)
        elif isinstance(command, _ProviderModelsRefreshed):
            self._provider_models_refreshed(command)
        elif isinstance(command, _ProviderModelsRefreshFailed):
            self._provider_models_refresh_failed(command)

    def _model_selection(self, *, refreshing: bool = False) -> ModelSelectionState:
        return ModelSelectionState(self._provider_name, self._available_models, self._model, refreshing=refreshing, custom_models=self._custom_models)

    def _provider_selection(self, *, reloading: bool = False) -> ProviderSelectionState:
        return ProviderSelectionState(self._provider_options, self._provider_name, reloading=reloading)

    def _select_provider_model(self, command: SelectProviderModel) -> None:
        if self._model_selection_presenter is None or self._settings_store is None:
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
            self._settings_store.save_settings((EnvironmentSetting(_model_env_name(self._provider_name), command.model),))
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
        self._provider_bindings[self._provider_name] = self._active_provider_binding
        self._provider_options = tuple(
            ProviderOption(option.provider_id, option.display_name, option.available_models, command.model, option.configured, option.custom_models)
            if option.provider_id == self._provider_name else option
            for option in self._provider_options
        )
        self._model_selection_presenter.set_model_selection(self._model_selection())
        if self._provider_selection_presenter is not None:
            self._provider_selection_presenter.set_provider_selection(self._provider_selection())

    def _select_provider(self, command: SelectProvider) -> None:
        if self._provider_selection_presenter is None or self._settings_store is None:
            return
        binding = self._provider_bindings.get(command.provider)
        option = next((item for item in self._provider_options if item.provider_id == command.provider), None)
        if binding is None or option is None or binding.readiness_issues:
            self._provider_selection_presenter.set_provider_selection(self._provider_selection())
            if self._operation_tracker is not None:
                self._operation_tracker.report_error("Provider switch rejected.", "Configure this provider's API key and try again.")
            self._open_provider_settings(command.provider)
            return
        if command.provider == self._provider_name:
            self._provider_selection_presenter.set_provider_selection(self._provider_selection())
            return
        try:
            self._settings_store.save_settings((EnvironmentSetting("CLIPAI_PROVIDER", command.provider),))
        except OSError:
            self._provider_selection_presenter.set_provider_selection(self._provider_selection())
            if self._operation_tracker is not None:
                self._operation_tracker.report_error("Could not save the provider selection.", "The previous provider remains active. Check .env permissions and try again.")
            return
        self._activate_provider(binding, option)

    def _activate_provider(self, binding: ProviderExecutionBinding, option: ProviderOption) -> None:
        self._active_provider_binding = binding
        self._provider_name = binding.provider_id
        self._model = binding.model
        self._available_models = option.available_models
        self._custom_models = option.custom_models
        if self._provider_selection_presenter is not None:
            self._provider_selection_presenter.set_provider_selection(self._provider_selection())
        if self._model_selection_presenter is not None:
            self._model_selection_presenter.set_model_selection(self._model_selection())

    def _reload_configuration(self) -> None:
        if self._reload_provider_settings is None:
            return
        if self._provider_selection_presenter is not None:
            self._provider_selection_presenter.set_provider_selection(self._provider_selection(reloading=True))
        try:
            snapshot = self._reload_provider_settings()
            bindings = {item.provider_id: item for item in snapshot.bindings}
            active = bindings[snapshot.active_provider]
            option = next(item for item in snapshot.options if item.provider_id == snapshot.active_provider)
            if active.readiness_issues:
                raise ValueError("active provider is not configured")
        except (ConfigError, OSError, ValueError, KeyError):
            if self._provider_selection_presenter is not None:
                self._provider_selection_presenter.set_provider_selection(self._provider_selection())
            if self._operation_tracker is not None:
                self._operation_tracker.report_error("Could not reload provider configuration.", "The previous provider remains active. Check .env and try again.")
            return
        self._provider_bindings = bindings
        self._provider_options = snapshot.options
        self._activate_provider(active, option)

    def _provider_settings_state(
        self,
        provider: str,
        *,
        operation_state: str = "idle",
        message: str = "",
        operation_id: str = "",
    ) -> ProviderSettingsState:
        option = next((item for item in self._provider_options if item.provider_id == provider), None)
        if option is None:
            option = next(item for item in self._provider_options if item.provider_id == self._provider_name)
        return ProviderSettingsState(
            self._provider_options,
            option.provider_id,
            option.selected_model,
            operation_state,  # type: ignore[arg-type]
            message,
            operation_id,
            self._gateway_name,
            self._gateway_base_url,
            option.provider_id == "gateway",
            option.provider_id == "gateway",
            option.provider_id == "gateway",
        )

    def _open_provider_settings(self, provider: str | None = None) -> None:
        if self._provider_settings_presenter is None:
            return
        selected = provider if provider and any(item.provider_id == provider for item in self._provider_options) else self._provider_name
        self._provider_settings_presenter.show_provider_settings(self._provider_settings_state(selected))

    def _validate_and_save_provider_settings(self, command: ValidateAndSaveProviderSettings) -> None:
        if (
            self._provider_settings_presenter is None
            or self._settings_store is None
            or self._validate_provider_credential is None
            or self._build_provider_candidate is None
        ):
            return
        option = next((item for item in self._provider_options if item.provider_id == command.provider), None)
        operation_id = command.operation_id or uuid.uuid4().hex
        model_allowed = command.model in option.available_models if option and option.provider_id != "gateway" else bool(command.model.strip())
        key_present = bool(command.api_key.strip()) or (option is not None and option.provider_id == "gateway")
        gateway_fields_valid = option is None or option.provider_id != "gateway" or bool(command.server_name.strip() and command.base_url.strip())
        if option is None or not model_allowed or not key_present or not gateway_fields_valid:
            self._provider_settings_presenter.set_provider_settings(
                self._provider_settings_state(command.provider, operation_state="failed", message="Provider, model, and API key are required.")
            )
            return
        self._provider_settings_operation_id = operation_id
        self._provider_settings_presenter.set_provider_settings(
            self._provider_settings_state(command.provider, operation_state="pending", message="Validating provider credentials...", operation_id=operation_id)
        )

        def work() -> None:
            try:
                self._validate_provider_credential(command.provider, command.api_key, command.base_url, command.model)
                candidate = self._build_provider_candidate(command.provider, command.model, command.api_key, command.server_name, command.base_url)
                updates = (
                        EnvironmentSetting("CLIPAI_PROVIDER", command.provider),
                        EnvironmentSetting("CLIPAI_GATEWAY_NAME", command.server_name.strip()),
                        EnvironmentSetting("CLIPAI_GATEWAY_BASE_URL", command.base_url.strip()),
                        EnvironmentSetting("CLIPAI_GATEWAY_API_KEY", command.api_key.strip()),
                        EnvironmentSetting("CLIPAI_GATEWAY_MODEL", command.model.strip()),
                    ) if command.provider == "gateway" else (
                        EnvironmentSetting("CLIPAI_PROVIDER", command.provider),
                        EnvironmentSetting(f"{command.provider.upper()}_API_KEY", command.api_key),
                        EnvironmentSetting(f"{command.provider.upper()}_MODEL", command.model),
                    )
                self._settings_store.save_settings(updates)
            except BaseException as exc:
                self.enqueue(_ProviderSettingsFailed(operation_id, _safe_provider_settings_error(exc)))
                return
            self.enqueue(_ProviderSettingsSaved(operation_id, candidate))

        self._supervisor.submit(
            f"provider-settings:{operation_id}",
            work,
            lambda error: self.enqueue(_ProviderSettingsFailed(operation_id, _safe_provider_settings_error(error))),
        )

    def _provider_settings_saved(self, command: _ProviderSettingsSaved) -> None:
        if command.operation_id != self._provider_settings_operation_id:
            return
        self._provider_settings_operation_id = ""
        self._provider_bindings = {item.provider_id: item for item in command.snapshot.bindings}
        self._provider_options = command.snapshot.options
        self._gateway_name = command.snapshot.gateway_name
        self._gateway_base_url = command.snapshot.gateway_base_url
        active = self._provider_bindings[command.snapshot.active_provider]
        option = next(item for item in self._provider_options if item.provider_id == command.snapshot.active_provider)
        self._activate_provider(active, option)
        if self._provider_settings_presenter is not None:
            self._provider_settings_presenter.set_provider_settings(
                self._provider_settings_state(active.provider_id, operation_state="succeeded", message="Provider settings saved.")
            )

    def _provider_settings_failed(self, command: _ProviderSettingsFailed) -> None:
        if command.operation_id != self._provider_settings_operation_id:
            return
        self._provider_settings_operation_id = ""
        if self._provider_settings_presenter is not None:
            self._provider_settings_presenter.set_provider_settings(
                self._provider_settings_state(self._provider_name, operation_state="failed", message=command.message)
            )
        if self._operation_tracker is not None:
            self._operation_tracker.report_error("Provider settings were not saved.", command.message)

    def _refresh_provider_models(self, command: RefreshProviderModels) -> None:
        if self._discover_provider_models is None:
            return
        provider = command.provider or self._provider_name
        option = next((item for item in self._provider_options if item.provider_id == provider), None)
        if option is None:
            return
        operation_id = command.operation_id or uuid.uuid4().hex
        self._model_refresh_operation_id = operation_id
        if provider == self._provider_name and self._model_selection_presenter is not None:
            self._model_selection_presenter.set_model_selection(self._model_selection(refreshing=True))
        if self._provider_settings_presenter is not None:
            self._provider_settings_presenter.set_provider_settings(
                self._provider_settings_state(provider, operation_state="pending", message="Refreshing model catalog...", operation_id=operation_id)
            )

        def work() -> None:
            try:
                models = tuple(dict.fromkeys(model.strip() for model in self._discover_provider_models(provider) if model.strip()))
                if not models:
                    raise ValueError("provider returned no models")
            except BaseException as exc:
                self.enqueue(_ProviderModelsRefreshFailed(operation_id, provider, _safe_model_refresh_error(exc)))
                return
            self.enqueue(_ProviderModelsRefreshed(operation_id, provider, models))

        self._supervisor.submit(
            f"provider-models:{operation_id}",
            work,
            lambda error: self.enqueue(_ProviderModelsRefreshFailed(operation_id, provider, _safe_model_refresh_error(error))),
        )

    def _provider_models_refreshed(self, command: _ProviderModelsRefreshed) -> None:
        if command.operation_id != self._model_refresh_operation_id:
            return
        self._model_refresh_operation_id = ""
        option = next(item for item in self._provider_options if item.provider_id == command.provider)
        models = command.models if option.selected_model in command.models else (option.selected_model, *command.models)
        custom_models = (option.selected_model,) if option.selected_model not in command.models else ()
        updated = ProviderOption(option.provider_id, option.display_name, models, option.selected_model, option.configured, custom_models)
        self._provider_options = tuple(updated if item.provider_id == command.provider else item for item in self._provider_options)
        if command.provider == self._provider_name:
            self._available_models = models
            self._custom_models = custom_models
            if self._model_selection_presenter is not None:
                self._model_selection_presenter.set_model_selection(self._model_selection())
        if self._provider_selection_presenter is not None:
            self._provider_selection_presenter.set_provider_selection(self._provider_selection())
        if self._provider_settings_presenter is not None:
            self._provider_settings_presenter.set_provider_settings(
                self._provider_settings_state(command.provider, operation_state="succeeded", message="Model catalog refreshed.")
            )

    def _provider_models_refresh_failed(self, command: _ProviderModelsRefreshFailed) -> None:
        if command.operation_id != self._model_refresh_operation_id:
            return
        self._model_refresh_operation_id = ""
        if command.provider == self._provider_name and self._model_selection_presenter is not None:
            self._model_selection_presenter.set_model_selection(self._model_selection())
        if self._provider_settings_presenter is not None:
            self._provider_settings_presenter.set_provider_settings(
                self._provider_settings_state(command.provider, operation_state="failed", message=command.message)
            )
        if self._operation_tracker is not None:
            self._operation_tracker.report_error("Could not refresh models.", command.message)

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


def _safe_provider_settings_error(error: BaseException) -> str:
    from ClipAI.core.errors import ConfigError, ProviderAuthError, ProviderResponseError, ProviderTimeoutError, ProviderUnavailableError

    if isinstance(error, ProviderAuthError):
        return "The provider rejected this API key. Check the key and try again."
    if isinstance(error, ProviderTimeoutError):
        return "Provider validation timed out. Try again."
    if isinstance(error, ProviderUnavailableError):
        return "Could not connect to the provider. Check the network and try again."
    if isinstance(error, ProviderResponseError):
        return str(error)
    if isinstance(error, ConfigError):
        return str(error)
    if isinstance(error, OSError):
        return "Could not write .env. Check file permissions and try again."
    return "Provider validation failed unexpectedly. Try again."


def _safe_model_refresh_error(error: BaseException) -> str:
    message = _safe_provider_settings_error(error)
    if message == "Provider validation failed unexpectedly. Try again.":
        return "The provider returned no usable models. The previous catalog remains active."
    return message


def _model_env_name(provider: str) -> str:
    return "CLIPAI_GATEWAY_MODEL" if provider == "gateway" else f"{provider.upper()}_MODEL"
