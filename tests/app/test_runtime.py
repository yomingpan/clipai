from __future__ import annotations

from ClipAI.app.runtime import AppRuntime
from ClipAI.core.commands import ArchiveResult, CloseSession, CopyResult, ExportDiagnostics, OpenProviderSettings, PasteResult, RefreshProviderModels, ReloadConfiguration, SelectProvider, SelectProviderModel, ShortcutTriggered, SpeakSelectionOrClipboard, StartAction, TogglePin, ToggleSpeech, ValidateAndSaveProviderSettings
from ClipAI.core.models import ActiveWorkflowContext, ActionDefinition, ModelSelectionState, ProviderOption, ProviderSelectionState, ProviderSettingsState, ReadinessIssue, ShortcutDefinition, WorkflowStep
from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.services.action_catalog import ActionCatalog
from ClipAI.services.shortcut_catalog import ShortcutCatalog
from ClipAI.providers.fake import FakeProvider
from ClipAI.services.provider_binding import ProviderExecutionBinding, ProviderRuntimeSnapshot


class FakeView:
    def __init__(self) -> None:
        self.snapshots: list[SessionSnapshot] = []
        self.sink = None
        self.stopped = False
        self.context: ActiveWorkflowContext | None = None
        self.output_results = []
        self.provider_settings_states = []

    def set_command_sink(self, sink) -> None:
        self.sink = sink

    def render(self, snapshot: SessionSnapshot) -> None:
        self.snapshots.append(snapshot)

    def run(self, command_pump) -> None:
        command_pump()

    def stop(self) -> None:
        self.stopped = True

    def active_workflow_context(self) -> ActiveWorkflowContext | None:
        return self.context

    def present_output_operation(self, result) -> None:
        self.output_results.append(result)

    def show_provider_settings(self, state) -> None:
        self.provider_settings_states.append(state)

    def set_provider_settings(self, state) -> None:
        self.provider_settings_states.append(state)


class FakeSupervisor:
    def __init__(self) -> None:
        self.work: dict[str, object] = {}
        self.cancelled: list[str] = []
        self.closed = False
        self.error_handlers: dict[str, object] = {}

    def submit(self, session_id, work, on_unhandled_error):
        self.work[session_id] = work
        self.error_handlers[session_id] = on_unhandled_error

    def cancel(self, session_id) -> None:
        self.cancelled.append(session_id)

    def shutdown(self) -> None:
        self.closed = True


class FakeExecute:
    def __init__(self) -> None:
        self.invocations = []
        self.models = []
        self.bindings = []

    def execute(self, action, controller) -> None:
        pass

    def execute_follow_up(self, action, text, controller) -> None:
        pass

    def execute_invocation(self, action, invocation, controller, *, binding) -> None:
        self.invocations.append(invocation)
        self.models.append(binding.model)
        self.bindings.append(binding)

    def execute_follow_up_invocation(self, *args, **kwargs) -> None:
        pass


class FakeOutputs:
    def __init__(self) -> None:
        self.copied: list[str] = []
        self.spoken: list[str] = []
        self.stops = 0
        self.can_speak = True
        self.can_paste = True
        self.can_archive = True
        self.pasted: list[str] = []
        self.archived: list[str] = []

    def copy(self, text: str) -> None:
        self.copied.append(text)

    def speak(self, text: str) -> None:
        self.spoken.append(text)

    def paste(self, text: str) -> None:
        self.pasted.append(text)

    def archive(self, text: str) -> None:
        self.archived.append(text)


class Listener:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class Tray:
    def __init__(self, on_exit) -> None:
        self.on_exit = on_exit
        self.started = False
        self.stopped = False
        self.model_selections = []
        self.provider_selections = []

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def set_model_selection(self, selection) -> None:
        self.model_selections.append(selection)

    def set_provider_selection(self, selection) -> None:
        self.provider_selections.append(selection)


class ModelPreferences:
    def __init__(self, error=None) -> None:
        self.saved = []
        self.error = error

    def save_settings(self, settings) -> None:
        if self.error:
            raise self.error
        self.saved.extend((setting.name, setting.value) for setting in settings)


class Operation:
    def __init__(self, events: list[tuple[str, ...]], operation_id: str) -> None:
        self.events = events
        self.operation_id = operation_id

    def succeed(self) -> None:
        self.events.append(("success", self.operation_id))

    def fail(self) -> None:
        self.events.append(("error", self.operation_id))

    def cancel(self) -> None:
        self.events.append(("cancel", self.operation_id))


class OperationTracker:
    def __init__(self) -> None:
        self.events: list[tuple[str, ...]] = []
        self.stopped = False

    def start(self, operation_id: str, kind: str):
        self.events.append(("start", operation_id, kind))
        return Operation(self.events, operation_id)

    def stop(self) -> None:
        self.stopped = True

    def report_error(self, message, suggestion="") -> None:
        self.events.append(("report_error", message, suggestion))

    def report_waiting(self) -> None:
        self.events.append(("waiting",))

    @property
    def last_error(self):
        return None


class Exporter:
    def __init__(self, destination="diagnostics.zip", error=None) -> None:
        self.destination = destination
        self.error = error

    def export(self):
        if self.error:
            raise self.error
        return self.destination


class Notifier:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def notify(self, title: str, message: str) -> None:
        self.messages.append((title, message))


class SpeechJob:
    operation_id = "tts:clipboard:unique"
    workflow_id = "global"

    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def run(self) -> None:
        self.calls.append("run")


class GlobalSpeech:
    def __init__(self) -> None:
        self.clipboard_only: list[bool] = []
        self.calls: list[str] = []
        self.cancelled = 0
        self.current = None

    def create_job(self, *, clipboard_only: bool) -> SpeechJob:
        self.clipboard_only.append(clipboard_only)
        self.current = (SpeechJob.operation_id, SpeechJob.workflow_id)
        return SpeechJob(self.calls)

    def cancel_current(self) -> None:
        if self.current is not None:
            self.cancel_operation(self.current[0])

    def cancel_operation(self, operation_id: str) -> bool:
        if self.current is None or self.current[0] != operation_id:
            return False
        self.current = None
        self.cancelled += 1
        return True

    @property
    def current_identity(self):
        return self.current


class PopupSpeech:
    def __init__(self, outputs: FakeOutputs) -> None:
        self.outputs = outputs
        self.current = None

    @property
    def current_identity(self):
        return self.current

    def operation_for(self, workflow_id):
        return self.current[0] if self.current and self.current[1] == workflow_id else None

    def create_text_job(self, *, operation_id, workflow_id, text):
        self.current = (operation_id, workflow_id)
        owner = self
        class Job:
            def run(self):
                owner.outputs.spoken.append(text)
                if owner.current == (operation_id, workflow_id):
                    owner.current = None
        return Job()

    def create_job(self, *, clipboard_only):
        del clipboard_only
        return SpeechJob([])

    def cancel_operation(self, operation_id):
        if self.current is None or self.current[0] != operation_id:
            return False
        self.current = None
        self.outputs.stops += 1
        return True

    def cancel_workflow(self, workflow_id):
        operation_id = self.operation_for(workflow_id)
        return self.cancel_operation(operation_id) if operation_id else False

    def cancel_current(self):
        if self.current:
            self.cancel_operation(self.current[0])


def make_runtime(*, with_tray: bool = False, operation_tracker=None, diagnostics_exporter=None, notifier=None, speech_coordinator=None, model_preferences=None, reload_provider_settings=None, validate_provider_credential=None, build_provider_candidate=None, discover_provider_models=None):
    action = ActionDefinition("a", "Action", "system", "{input}", {})
    shorten = ActionDefinition("shorten", "Shorten", "system", "{input}", {})
    view = FakeView()
    supervisor = FakeSupervisor()
    outputs = FakeOutputs()
    speech_coordinator = speech_coordinator or PopupSpeech(outputs)
    listener = Listener()
    runtime = AppRuntime(
        actions=ActionCatalog([action, shorten]),
        shortcuts=ShortcutCatalog([
            ShortcutDefinition("a", "ctrl+alt+8", "start_action", "a"),
            ShortcutDefinition("speech", "ctrl+alt+q", "speak_selection_or_clipboard"),
            ShortcutDefinition("shorten", "ctrl+alt+x", "start_action", "shorten"),
        ]),
        execute_action=FakeExecute(),
        output_actions=outputs,
        view=view,
        supervisor=supervisor,
        provider_binding=ProviderExecutionBinding(FakeProvider(), "openai", "model"),
        hotkey_registrar=lambda _map, _callback: listener,
        tray_factory=Tray if with_tray else None,
        operation_tracker=operation_tracker,
        diagnostics_exporter=diagnostics_exporter,
        notifier=notifier,
        speech_coordinator=speech_coordinator,
        workflow_context_reader=view,
        output_operation_presenter=view,
        available_models=("model", "new-model"),
        settings_store=model_preferences,
        provider_options=(
            ProviderOption("openai", "OpenAI", ("model", "new-model"), "model", True),
            ProviderOption("gemini", "Gemini", ("gemini-model",), "gemini-model", True),
        ),
        provider_bindings=(
            ProviderExecutionBinding(FakeProvider(), "openai", "model"),
            ProviderExecutionBinding(FakeProvider(), "gemini", "gemini-model"),
        ),
        reload_provider_settings=reload_provider_settings,
        provider_settings_presenter=view,
        validate_provider_credential=validate_provider_credential,
        build_provider_candidate=build_provider_candidate,
        discover_provider_models=discover_provider_models,
    )
    return runtime, view, supervisor, outputs, listener


def test_model_selection_persists_before_switching_new_workflows() -> None:
    preferences = ModelPreferences()
    runtime, view, supervisor, _outputs, _listener = make_runtime(model_preferences=preferences)
    presenter = Tray(lambda: None)
    runtime._model_selection_presenter = presenter
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    first_id = view.snapshots[-1].session_id
    first_work = supervisor.work[runtime._workflows[first_id].snapshot.active_invocation_id]
    runtime.enqueue(SelectProviderModel("openai", "new-model"))
    runtime.drain_commands()
    first_work()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    second_id = view.snapshots[-1].session_id
    supervisor.work[runtime._workflows[second_id].snapshot.active_invocation_id]()
    assert preferences.saved == [("OPENAI_MODEL", "new-model")]
    assert runtime._execute_action.models == ["model", "new-model"]
    assert presenter.model_selections[-1] == ModelSelectionState("openai", ("model", "new-model"), "new-model")


def test_workflow_captures_provider_binding_before_runtime_switch() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    first_id = view.snapshots[-1].session_id
    first_work = supervisor.work[runtime._workflows[first_id].snapshot.active_invocation_id]

    replacement = ProviderExecutionBinding(FakeProvider("replacement"), "gemini", "gemini-model")
    runtime._active_provider_binding = replacement
    runtime._model = replacement.model
    runtime._provider_name = replacement.provider_id
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    second_id = view.snapshots[-1].session_id
    second_work = supervisor.work[runtime._workflows[second_id].snapshot.active_invocation_id]

    first_work()
    second_work()
    assert [(item.provider_id, item.model) for item in runtime._execute_action.bindings] == [
        ("openai", "model"),
        ("gemini", "gemini-model"),
    ]


def test_model_selection_write_failure_keeps_previous_model() -> None:
    operations = OperationTracker()
    runtime, _view, _supervisor, _outputs, _listener = make_runtime(
        operation_tracker=operations,
        model_preferences=ModelPreferences(OSError("denied")),
    )
    presenter = Tray(lambda: None)
    runtime._model_selection_presenter = presenter
    runtime.enqueue(SelectProviderModel("openai", "new-model"))
    runtime.drain_commands()
    assert runtime._model == "model"
    assert presenter.model_selections[-1].selected_model == "model"
    assert operations.events[-1][0] == "report_error"


def test_provider_selection_persists_before_switching_new_workflows() -> None:
    preferences = ModelPreferences()
    runtime, _view, _supervisor, _outputs, _listener = make_runtime(model_preferences=preferences)
    presenter = Tray(lambda: None)
    runtime._provider_selection_presenter = presenter
    runtime._model_selection_presenter = presenter
    runtime.enqueue(SelectProvider("gemini"))
    runtime.drain_commands()
    assert preferences.saved == [("CLIPAI_PROVIDER", "gemini")]
    assert runtime._active_provider_binding.provider_id == "gemini"
    assert presenter.provider_selections[-1].selected_provider == "gemini"
    assert presenter.model_selections[-1] == ModelSelectionState("gemini", ("gemini-model",), "gemini-model")


def test_reload_failure_keeps_previous_provider() -> None:
    operations = OperationTracker()
    runtime, _view, _supervisor, _outputs, _listener = make_runtime(
        operation_tracker=operations,
        reload_provider_settings=lambda: (_ for _ in ()).throw(ValueError("bad env")),
    )
    presenter = Tray(lambda: None)
    runtime._provider_selection_presenter = presenter
    runtime.enqueue(ReloadConfiguration())
    runtime.drain_commands()
    assert runtime._provider_name == "openai"
    assert operations.events[-1][0] == "report_error"


def test_reload_success_replaces_catalog_and_active_binding() -> None:
    option = ProviderOption("gemini", "Gemini", ("fresh",), "fresh", True)
    binding = ProviderExecutionBinding(FakeProvider(), "gemini", "fresh")
    runtime, _view, _supervisor, _outputs, _listener = make_runtime(
        reload_provider_settings=lambda: ProviderRuntimeSnapshot("gemini", (binding,), (option,)),
    )
    presenter = Tray(lambda: None)
    runtime._provider_selection_presenter = presenter
    runtime._model_selection_presenter = presenter
    runtime.enqueue(ReloadConfiguration())
    runtime.drain_commands()
    assert runtime._provider_name == "gemini"
    assert runtime._model == "fresh"
    assert presenter.provider_selections[-1] == ProviderSelectionState((option,), "gemini")


def test_provider_without_key_is_rejected_without_persistence() -> None:
    preferences = ModelPreferences()
    operations = OperationTracker()
    runtime, _view, _supervisor, _outputs, _listener = make_runtime(
        model_preferences=preferences,
        operation_tracker=operations,
    )
    runtime._provider_bindings["gemini"] = ProviderExecutionBinding(
        FakeProvider(),
        "gemini",
        "gemini-model",
        (ReadinessIssue("missing", "missing", "llm"),),
    )
    presenter = Tray(lambda: None)
    runtime._provider_selection_presenter = presenter
    runtime.enqueue(SelectProvider("gemini"))
    runtime.drain_commands()
    assert preferences.saved == []
    assert runtime._provider_name == "openai"
    assert operations.events[-1][0] == "report_error"
    assert runtime._view.provider_settings_states[-1].selected_provider == "gemini"


def test_provider_settings_validate_then_save_and_activate() -> None:
    preferences = ModelPreferences()
    validated: list[tuple[str, str]] = []
    option = ProviderOption("gemini", "Gemini", ("gemini-model",), "gemini-model", True)
    binding = ProviderExecutionBinding(FakeProvider(), "gemini", "gemini-model")
    candidate = ProviderRuntimeSnapshot("gemini", (binding,), (option,))
    runtime, view, supervisor, _outputs, _listener = make_runtime(
        model_preferences=preferences,
        validate_provider_credential=lambda provider, key, _base_url, _model: validated.append((provider, key)),
        build_provider_candidate=lambda _provider, _model, _key, _name, _base_url: candidate,
    )
    command = ValidateAndSaveProviderSettings("gemini", "gemini-model", "top-secret", "save-1")
    assert "top-secret" not in repr(command)
    runtime.enqueue(command)
    runtime.drain_commands()
    assert view.provider_settings_states[-1].operation_state == "pending"
    supervisor.work["provider-settings:save-1"]()
    runtime.drain_commands()
    assert validated == [("gemini", "top-secret")]
    assert preferences.saved == [
        ("CLIPAI_PROVIDER", "gemini"),
        ("GEMINI_API_KEY", "top-secret"),
        ("GEMINI_MODEL", "gemini-model"),
    ]
    assert runtime._provider_name == "gemini"
    assert view.provider_settings_states[-1].operation_state == "succeeded"


def test_late_provider_settings_failure_cannot_replace_newer_state() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime(
        model_preferences=ModelPreferences(),
        validate_provider_credential=lambda _provider, _key, _base_url, _model: (_ for _ in ()).throw(RuntimeError("failed")),
        build_provider_candidate=lambda _provider, _model, _key, _name, _base_url: (_ for _ in ()).throw(AssertionError()),
    )
    runtime.enqueue(ValidateAndSaveProviderSettings("gemini", "gemini-model", "first", "old"))
    runtime.drain_commands()
    runtime.enqueue(ValidateAndSaveProviderSettings("gemini", "gemini-model", "second", "new"))
    runtime.drain_commands()
    supervisor.work["provider-settings:old"]()
    runtime.drain_commands()
    assert view.provider_settings_states[-1].operation_id == "new"


def test_gateway_settings_allow_empty_key_and_save_single_profile() -> None:
    preferences = ModelPreferences()
    validated = []
    option = ProviderOption("gateway", "Local AI", ("local-model",), "local-model", True)
    binding = ProviderExecutionBinding(FakeProvider(), "gateway", "local-model")
    candidate = ProviderRuntimeSnapshot("gateway", (binding,), (option,), "Local AI", "http://localhost:8000/v1")
    runtime, view, supervisor, _outputs, _listener = make_runtime(
        model_preferences=preferences,
        validate_provider_credential=lambda provider, key, base_url, model: validated.append((provider, key, base_url, model)),
        build_provider_candidate=lambda _provider, _model, _key, _name, _base_url: candidate,
    )
    runtime._provider_options = (*runtime._provider_options, ProviderOption("gateway", "Custom Gateway", (), "", False))
    command = ValidateAndSaveProviderSettings(
        "gateway",
        "local-model",
        "",
        "gateway-save",
        "Local AI",
        "http://localhost:8000",
    )
    secret_url_command = ValidateAndSaveProviderSettings("gateway", "model", "", base_url="https://gateway.test?token=hidden")
    assert "token=hidden" not in repr(secret_url_command)
    runtime.enqueue(command)
    runtime.drain_commands()
    supervisor.work["provider-settings:gateway-save"]()
    runtime.drain_commands()
    assert validated == [("gateway", "", "http://localhost:8000", "local-model")]
    assert preferences.saved == [
        ("CLIPAI_PROVIDER", "gateway"),
        ("CLIPAI_GATEWAY_NAME", "Local AI"),
        ("CLIPAI_GATEWAY_BASE_URL", "http://localhost:8000"),
        ("CLIPAI_GATEWAY_MODEL", "local-model"),
    ]
    assert runtime._provider_name == "gateway"
    assert view.provider_settings_states[-1].operation_state == "succeeded"


def test_refresh_models_replaces_catalog_but_keeps_current_model() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime(
        discover_provider_models=lambda provider, _connection: ("remote-a", "remote-a", "remote-b") if provider == "openai" else (),
    )
    presenter = Tray(lambda: None)
    runtime._model_selection_presenter = presenter
    runtime.enqueue(RefreshProviderModels("openai", "refresh-1"))
    runtime.drain_commands()
    assert presenter.model_selections[-1].refreshing is True
    supervisor.work["provider-models:refresh-1"]()
    runtime.drain_commands()
    assert runtime._available_models == ("model", "remote-a", "remote-b")
    assert presenter.model_selections[-1].refreshing is False
    assert view.provider_settings_states[-1].operation_state == "succeeded"


def test_provider_settings_model_change_keeps_existing_api_key() -> None:
    preferences = ModelPreferences()
    validated = []
    binding = ProviderExecutionBinding(FakeProvider(), "gemini", "gemini-model")
    candidate = ProviderRuntimeSnapshot("gemini", (binding,), (ProviderOption("gemini", "Gemini", ("gemini-model",), "gemini-model", True),))
    runtime, _view, supervisor, _outputs, _listener = make_runtime(
        model_preferences=preferences,
        validate_provider_credential=lambda provider, key, _base_url, _model: validated.append((provider, key)),
        build_provider_candidate=lambda _provider, _model, _key, _name, _base_url: candidate,
    )

    runtime.enqueue(ValidateAndSaveProviderSettings("gemini", "gemini-model", "", "keep-key"))
    runtime.drain_commands()
    supervisor.work["provider-settings:keep-key"]()
    runtime.drain_commands()

    assert validated == [("gemini", "")]
    assert preferences.saved == [("CLIPAI_PROVIDER", "gemini"), ("GEMINI_MODEL", "gemini-model")]


def test_opening_selected_provider_reloads_credential_hint_without_activating_it() -> None:
    openai_option = ProviderOption("openai", "OpenAI", ("model",), "model", True, credential_hint="••••old1")
    gemini_option = ProviderOption("gemini", "Gemini", ("gemini-model",), "gemini-model", True, credential_hint="••••new2")
    snapshot = ProviderRuntimeSnapshot(
        "openai",
        (
            ProviderExecutionBinding(FakeProvider(), "openai", "model"),
            ProviderExecutionBinding(FakeProvider(), "gemini", "gemini-model"),
        ),
        (openai_option, gemini_option),
    )
    runtime, view, _supervisor, _outputs, _listener = make_runtime(reload_provider_settings=lambda: snapshot)

    runtime.enqueue(OpenProviderSettings("gemini"))
    runtime.drain_commands()

    state = view.provider_settings_states[-1]
    selected = next(item for item in state.providers if item.provider_id == "gemini")
    assert state.selected_provider == "gemini"
    assert selected.credential_hint == "••••new2"
    assert runtime._provider_name == "openai"


def test_provider_switch_reloads_binding_before_activation() -> None:
    preferences = ModelPreferences()
    refreshed = ProviderExecutionBinding(FakeProvider(), "gemini", "fresh-model")
    snapshot = ProviderRuntimeSnapshot(
        "openai",
        (
            ProviderExecutionBinding(FakeProvider(), "openai", "model"),
            refreshed,
        ),
        (
            ProviderOption("openai", "OpenAI", ("model",), "model", True),
            ProviderOption("gemini", "Gemini", ("fresh-model",), "fresh-model", True, credential_hint="••••new2"),
        ),
    )
    runtime, _view, _supervisor, _outputs, _listener = make_runtime(
        model_preferences=preferences,
        reload_provider_settings=lambda: snapshot,
    )
    presenter = Tray(lambda: None)
    runtime._provider_selection_presenter = presenter
    runtime._model_selection_presenter = presenter

    runtime.enqueue(SelectProvider("gemini"))
    runtime.drain_commands()

    assert runtime._active_provider_binding is refreshed
    assert runtime._model == "fresh-model"


def test_gateway_refresh_uses_unsaved_connection_without_writing_settings() -> None:
    preferences = ModelPreferences()
    received = []
    runtime, _view, supervisor, _outputs, _listener = make_runtime(
        model_preferences=preferences,
        discover_provider_models=lambda provider, connection: received.append((provider, connection)) or ("gateway-a", "gateway-b"),
    )
    runtime._provider_options = (*runtime._provider_options, ProviderOption("gateway", "Gateway", (), "", False))
    from ClipAI.core.models import ModelCatalogConnection

    runtime.enqueue(RefreshProviderModels("gateway", "gateway-refresh", ModelCatalogConnection("http://localhost:8000", "secret", "fallback")))
    runtime.drain_commands()
    supervisor.work["provider-models:gateway-refresh"]()
    runtime.drain_commands()

    assert received == [("gateway", ModelCatalogConnection("http://localhost:8000", "secret", "fallback"))]
    assert preferences.saved == []
    option = next(item for item in runtime._provider_options if item.provider_id == "gateway")
    assert option.available_models == ("gateway-a", "gateway-b")


def test_refresh_failure_keeps_previous_catalog() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime(discover_provider_models=lambda _provider, _connection: ())
    presenter = Tray(lambda: None)
    runtime._model_selection_presenter = presenter
    runtime.enqueue(RefreshProviderModels("openai", "refresh-empty"))
    runtime.drain_commands()
    supervisor.work["provider-models:refresh-empty"]()
    runtime.drain_commands()
    assert runtime._available_models == ("model", "new-model")
    assert view.provider_settings_states[-1].operation_state == "failed"


def test_late_model_refresh_result_cannot_replace_newer_catalog() -> None:
    calls = iter((("old-model",), ("new-model-remote",)))
    runtime, _view, supervisor, _outputs, _listener = make_runtime(discover_provider_models=lambda _provider, _connection: next(calls))
    runtime.enqueue(RefreshProviderModels("openai", "old-refresh"))
    runtime.drain_commands()
    runtime.enqueue(RefreshProviderModels("openai", "new-refresh"))
    runtime.drain_commands()
    supervisor.work["provider-models:old-refresh"]()
    runtime.drain_commands()
    assert runtime._available_models == ("model", "new-model")
    supervisor.work["provider-models:new-refresh"]()
    runtime.drain_commands()
    assert runtime._available_models == ("model", "new-model-remote")


def test_gateway_model_selection_uses_clipai_env_name() -> None:
    preferences = ModelPreferences()
    runtime, _view, _supervisor, _outputs, _listener = make_runtime(model_preferences=preferences)
    binding = ProviderExecutionBinding(FakeProvider(), "gateway", "old")
    runtime._active_provider_binding = binding
    runtime._provider_bindings["gateway"] = binding
    runtime._provider_name = "gateway"
    runtime._model = "old"
    runtime._available_models = ("old", "new")
    runtime._provider_options = (ProviderOption("gateway", "Gateway", ("old", "new"), "old", True),)
    presenter = Tray(lambda: None)
    runtime._model_selection_presenter = presenter
    runtime.enqueue(SelectProviderModel("gateway", "new"))
    runtime.drain_commands()
    assert preferences.saved == [("CLIPAI_GATEWAY_MODEL", "new")]


def test_global_speech_command_is_supervised_without_creating_session() -> None:
    speech = GlobalSpeech()
    runtime, view, supervisor, _outputs, _listener = make_runtime(speech_coordinator=speech)
    runtime.enqueue(SpeakSelectionOrClipboard())
    runtime.drain_commands()
    assert speech.clipboard_only == [False]
    assert view.snapshots == []
    work = supervisor.work["speech:tts:clipboard:unique"]
    work()
    assert speech.calls == ["run"]


def test_global_speech_shortcut_stops_active_speech_without_starting_another_job() -> None:
    speech = GlobalSpeech()
    runtime, view, supervisor, _outputs, _listener = make_runtime(speech_coordinator=speech)
    runtime.enqueue(ShortcutTriggered("speech", "short"))
    runtime.drain_commands()

    runtime.enqueue(ShortcutTriggered("speech", "short"))
    runtime.drain_commands()

    assert speech.clipboard_only == [False]
    assert speech.cancelled == 1
    assert speech.current_identity is None
    assert supervisor.cancelled == [SpeechJob.operation_id]
    assert [(result.operation_id, result.state) for result in view.output_results] == [
        (SpeechJob.operation_id, "pending"),
        (SpeechJob.operation_id, "cancelled"),
    ]


def test_long_speech_shortcut_keeps_active_speech_and_arms_sequence() -> None:
    speech = GlobalSpeech()
    runtime, _view, _supervisor, _outputs, _listener = make_runtime(speech_coordinator=speech)
    runtime.enqueue(ShortcutTriggered("speech", "short"))
    runtime.drain_commands()

    runtime.enqueue(ShortcutTriggered("speech", "long"))
    runtime.drain_commands()

    assert speech.current_identity == (SpeechJob.operation_id, SpeechJob.workflow_id)
    assert speech.cancelled == 0
    assert speech.clipboard_only == [False]


def test_global_speech_uses_clipboard_only_when_session_exists() -> None:
    speech = GlobalSpeech()
    runtime, _view, _supervisor, _outputs, _listener = make_runtime(speech_coordinator=speech)
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    runtime.enqueue(SpeakSelectionOrClipboard())
    runtime.drain_commands()
    assert speech.clipboard_only == [True]


def test_contextual_action_reuses_active_workflow_and_prefers_popup_selection() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    workflow_id = view.snapshots[-1].session_id
    controller = runtime._workflows[workflow_id]
    old_invocation = controller.snapshot.active_invocation_id
    step = WorkflowStep("step-1", "a", "Action", "input", "full popup result", "plain_text")
    controller._snapshot = controller.snapshot.evolve(
        status=SessionStatus.COMPLETED,
        content=step.result_text,
        steps=(step,),
        displayed_step_index=0,
        active_invocation_id=None,
    )
    view.context = ActiveWorkflowContext(workflow_id, step.step_id, step.result_text, "selected popup text")

    runtime.enqueue(StartAction("shorten", "long"))
    runtime.drain_commands()

    assert len(runtime._workflows) == 1
    assert runtime._foreground_id == workflow_id
    new_invocation = controller.snapshot.active_invocation_id
    assert new_invocation != old_invocation
    supervisor.work[new_invocation]()
    invocation = runtime._execute_action.invocations[-1]
    assert invocation.input_target.document.text == "selected popup text"
    assert invocation.parent_step_id == "step-1"


def test_contextual_action_without_popup_context_creates_external_workflow() -> None:
    runtime, _view, _supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("shorten", "short"))
    runtime.drain_commands()
    controller = next(iter(runtime._workflows.values()))
    assert controller.snapshot.active_invocation_id is not None


def test_speech_sequence_is_headless_and_prefers_popup_selection() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    popup_id = view.snapshots[-1].session_id
    controller = runtime._workflows[popup_id]
    step = WorkflowStep("step-1", "a", "Action", "input", "full popup result", "plain_text")
    controller._snapshot = controller.snapshot.evolve(
        status=SessionStatus.COMPLETED,
        content=step.result_text,
        steps=(step,),
        displayed_step_index=0,
        active_invocation_id=None,
    )
    view.context = ActiveWorkflowContext(popup_id, step.step_id, step.result_text, "selected popup text")
    rendered_before = len(view.snapshots)

    runtime.enqueue(StartAction("a", "short", "speech"))
    runtime.drain_commands()
    speech_id = runtime._sequence_workflow_id
    assert speech_id is not None
    supervisor.work[runtime._workflows[speech_id].snapshot.active_invocation_id]()

    invocation = runtime._execute_action.invocations[-1]
    assert invocation.result_route == "speech"
    assert invocation.input_target.document.text == "selected popup text"
    assert len(view.snapshots) == rendered_before


def test_latest_start_cancels_previous_unpinned_session() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    first_id = view.snapshots[-1].session_id
    first_invocation = runtime._workflows[first_id].snapshot.active_invocation_id
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    assert first_invocation in supervisor.cancelled
    assert any(s.session_id == first_id and s.status == SessionStatus.CANCELLED for s in view.snapshots)


def test_completed_pinned_session_survives_new_start() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    controller = runtime._workflows[session_id]
    controller._snapshot = controller.snapshot.evolve(status=SessionStatus.COMPLETED, content="saved")
    runtime.enqueue(TogglePin(session_id))
    runtime.drain_commands()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    assert session_id not in supervisor.cancelled
    assert controller.snapshot.pinned is True


def test_copy_and_close_are_commands() -> None:
    runtime, view, supervisor, outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    controller = runtime._workflows[session_id]
    active_invocation = controller.snapshot.active_invocation_id
    controller._snapshot = controller.snapshot.evolve(content="clean result")
    runtime.enqueue(CopyResult(session_id, operation_id="copy-op"))
    runtime.enqueue(CloseSession(session_id))
    runtime.drain_commands()
    supervisor.work["copy-op"]()
    assert outputs.copied == ["clean result"]
    assert active_invocation in supervisor.cancelled
    assert session_id not in runtime._workflows


def test_copy_prefers_selected_command_text() -> None:
    runtime, view, _supervisor, outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    runtime._workflows[session_id]._snapshot = runtime._workflows[session_id].snapshot.evolve(content="full result")
    runtime.enqueue(CopyResult(session_id, " selected ", "copy-op"))
    runtime.drain_commands()
    _supervisor.work["copy-op"]()
    assert outputs.copied == ["selected"]


def test_stop_releases_listener_supervisor_and_view() -> None:
    runtime, view, supervisor, _outputs, listener = make_runtime()
    runtime.start()
    runtime.stop()
    assert listener.stopped and supervisor.closed and view.stopped


def test_tray_exit_uses_typed_shutdown_command() -> None:
    runtime, view, supervisor, _outputs, listener = make_runtime(with_tray=True)
    runtime.start()
    tray = runtime._tray
    assert tray is not None and tray.started
    tray.on_exit()
    runtime.drain_commands()
    assert tray.stopped and listener.stopped and supervisor.closed and view.stopped


def test_speech_runs_as_supervised_output_and_can_stop() -> None:
    runtime, view, supervisor, outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    controller = runtime._workflows[session_id]
    controller._snapshot = controller.snapshot.evolve(content="speak me")
    runtime.enqueue(ToggleSpeech(session_id))
    runtime.drain_commands()
    assert controller.snapshot.speaking is True
    operation_id = runtime._speech_coordinator.operation_for(session_id)
    work = supervisor.work[operation_id]
    work()
    assert outputs.spoken == ["speak me"]
    assert controller.snapshot.speaking is False


def test_global_speech_shortcut_stops_popup_speech_and_resets_speaker_state() -> None:
    runtime, view, supervisor, outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    controller = runtime._workflows[session_id]
    controller._snapshot = controller.snapshot.evolve(content="speak me")
    runtime.enqueue(ToggleSpeech(session_id, operation_id="popup-speech"))
    runtime.drain_commands()
    assert controller.snapshot.speaking is True

    runtime.enqueue(ShortcutTriggered("speech", "short"))
    runtime.drain_commands()

    assert runtime._speech_coordinator.current_identity is None
    assert controller.snapshot.speaking is False
    assert outputs.stops == 1
    assert supervisor.cancelled == ["popup-speech"]


def test_late_completion_from_stopped_speech_cannot_clear_new_speaker_state() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    controller = runtime._workflows[session_id]
    controller._snapshot = controller.snapshot.evolve(content="speak me")
    runtime.enqueue(ToggleSpeech(session_id, operation_id="old-speech"))
    runtime.drain_commands()
    old_work = supervisor.work["old-speech"]

    runtime.enqueue(SpeakSelectionOrClipboard())
    runtime.enqueue(ToggleSpeech(session_id, operation_id="new-speech"))
    runtime.drain_commands()
    old_work()

    assert runtime._speech_coordinator.current_identity == ("new-speech", session_id)
    assert controller.snapshot.speaking is True


def test_speech_prefers_selected_command_text() -> None:
    runtime, view, supervisor, outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    runtime._workflows[session_id]._snapshot = runtime._workflows[session_id].snapshot.evolve(content="full")
    runtime.enqueue(ToggleSpeech(session_id, "selected"))
    runtime.drain_commands()
    supervisor.work[runtime._speech_coordinator.operation_for(session_id)]()
    assert outputs.spoken == ["selected"]


def test_speech_reports_one_external_api_lifecycle() -> None:
    operations = OperationTracker()
    runtime, view, supervisor, _outputs, _listener = make_runtime(operation_tracker=operations)
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    runtime._workflows[session_id]._snapshot = runtime._workflows[session_id].snapshot.evolve(content="speak")
    runtime.enqueue(ToggleSpeech(session_id))
    runtime.drain_commands()
    operation_id = runtime._speech_coordinator.operation_for(session_id)
    supervisor.work[operation_id]()
    assert operations.events == [("start", f"tts:{operation_id}", "tts"), ("success", f"tts:{operation_id}")]


def test_closing_old_popup_cannot_stop_newer_popup_speech() -> None:
    runtime, view, _supervisor, outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    first_id = view.snapshots[-1].session_id
    first = runtime._workflows[first_id]
    first._snapshot = first.snapshot.evolve(status=SessionStatus.COMPLETED, content="first")
    runtime.enqueue(TogglePin(first_id))
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    second_id = view.snapshots[-1].session_id
    second = runtime._workflows[second_id]
    second._snapshot = second.snapshot.evolve(status=SessionStatus.COMPLETED, content="second")

    runtime.enqueue(ToggleSpeech(first_id, operation_id="speech-a"))
    runtime.enqueue(ToggleSpeech(second_id, operation_id="speech-b"))
    runtime.drain_commands()
    stops_after_replacement = outputs.stops
    runtime.enqueue(CloseSession(first_id))
    runtime.drain_commands()

    assert runtime._speech_coordinator.operation_for(second_id) == "speech-b"
    assert outputs.stops == stops_after_replacement


def test_diagnostics_export_is_typed_supervised_work_with_feedback() -> None:
    notifier = Notifier()
    runtime, _view, supervisor, _outputs, _listener = make_runtime(
        diagnostics_exporter=Exporter("C:/diagnostics/report.zip"),
        notifier=notifier,
    )
    runtime.enqueue(ExportDiagnostics())
    runtime.drain_commands()
    supervisor.work["diagnostics:export"]()
    assert notifier.messages == [("ClipAI Diagnostics", "Exported to C:/diagnostics/report.zip")]


def test_diagnostics_export_failure_reports_incident() -> None:
    notifier = Notifier()
    runtime, _view, supervisor, _outputs, _listener = make_runtime(
        diagnostics_exporter=Exporter(error=OSError("disk full")),
        notifier=notifier,
    )
    runtime.enqueue(ExportDiagnostics())
    runtime.drain_commands()
    try:
        supervisor.work["diagnostics:export"]()
    except OSError as error:
        supervisor.error_handlers["diagnostics:export"](error)
    assert "Export failed. Incident:" in notifier.messages[-1][1]


def test_paste_and_archive_flow_through_typed_commands() -> None:
    runtime, view, _supervisor, outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    controller = runtime._workflows[session_id]
    controller._snapshot = controller.snapshot.evolve(content="use me")
    runtime.enqueue(ArchiveResult(session_id, operation_id="archive-op"))
    runtime.drain_commands()
    _supervisor.work["archive-op"]()
    assert outputs.archived == ["use me"]
    runtime.enqueue(PasteResult(session_id, "selected", "paste-op"))
    runtime.drain_commands()
    assert session_id in runtime._workflows
    _supervisor.work["paste-op"]()
    runtime.drain_commands()
    assert session_id not in runtime._workflows
    assert outputs.pasted == ["selected"]
