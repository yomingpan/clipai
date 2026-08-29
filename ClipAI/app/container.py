from __future__ import annotations

from collections.abc import Callable, Sequence
from importlib.metadata import PackageNotFoundError, version
import os
from pathlib import Path
import uuid

from ClipAI.app.config_schema import ConfigBundle
from ClipAI.core.errors import ConfigError
from ClipAI.app.provider_configuration import AppProviderConfigurationBackend, build_provider_snapshot
from ClipAI.app.provider_execution import ProviderExecutionModule
from ClipAI.app.readiness import assess_provider_readiness
from ClipAI.app.runtime import AppRuntime
from ClipAI.app.runtime_outputs import ResultOutputRuntimeModule
from ClipAI.app.runtime_provider_configuration import ProviderConfigurationRuntimeModule
from ClipAI.app.runtime_shortcut_guide import ShortcutGuideRuntimeModule
from ClipAI.app.runtime_action_feedback import ActionFeedbackRuntimeModule
from ClipAI.app.runtime_user_preferences import UserPreferencesRuntimeModule
from ClipAI.app.runtime_voice_input import VoiceInputRuntimeModule
from ClipAI.app.owned_processes import AppOwnedProcessRegistry
from ClipAI.app.runtime_workflows import WorkflowRuntimeModule
from ClipAI.app.speech_execution import SupervisedSpeechResultSink
from ClipAI.core.commands import DisableVoiceInput, ExportDiagnostics, ExternalForegroundChanged, OpenPersonalStyles, OpenProviderSettings, OpenShortcutGuide, OpenVoicePermissionSettings, OpenVoiceSetup, ResetFirstUseHints, SetFirstUseHintsEnabled, SetSpeechSpeed, SetVoiceLanguage, ShortcutInputEvent, ShutdownApplication, VoiceDisablePreferenceSaved, VoiceEngineEventReceived, VoiceLanguagePreferenceSaved, VoicePreferenceSaved
from ClipAI.core.models import ModelSelectionState, ProviderSelectionState, ReadinessIssue
from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.ports import LLMProvider, ShortcutInput
from ClipAI.platform.clipboard import SystemClipboard
from ClipAI.platform.action_feedback import JsonlActionFeedbackStore
from ClipAI.platform.user_preferences import JsonUserPreferencesStore
from ClipAI.platform.personal_styles import JsonPersonalStyleStore, Utf8PersonalStyleFileReader
from ClipAI.platform.hotkey import register_hotkeys_with_long_press
from ClipAI.platform.selection import SystemSelectionCaptureAdapter
from ClipAI.platform.filesystem import JsonlArchiveStore
from ClipAI.platform.dotenv_preferences import DotenvModelPreferenceStore
from ClipAI.platform.display import WindowsDisplayMetricsReader
from ClipAI.platform.speech import EdgeSpeechOutput
from ClipAI.platform.keyboard import SystemKeyboardOutput
from ClipAI.platform.native_window import WindowsNativeWindowSurface
from ClipAI.platform.pointer_input import WindowsPointerPressReader
from ClipAI.platform.window_focus import WindowsForegroundWindowMonitor
from ClipAI.platform.browser_speech import BrowserSpeechWebView2Engine
from ClipAI.platform.voice_permissions import open_microphone_privacy_settings
from ClipAI.providers.fake import FakeProvider
from ClipAI.providers.gateway import OpenAICompatibleGatewayProvider
from ClipAI.providers.anthropic import AnthropicProvider
from ClipAI.providers.gemini import GeminiProvider
from ClipAI.providers.http_transport import HttpTransport, HttpxAsyncTransport
from ClipAI.providers.openai import OpenAIProvider
from ClipAI.providers.settings import ProviderCredential
from ClipAI.services.execute_action import ActionExecutor
from ClipAI.services.clipboard_transaction import ClipboardTransactionCoordinator
from ClipAI.services.action_feedback import ActionFeedbackService
from ClipAI.services.user_preferences import UserPreferencesCoordinator
from ClipAI.services.personal_styles import PersonalStyleCoordinator
from ClipAI.services.provider_binding import ProviderRuntimeSnapshot
from ClipAI.services.provider_configuration import ProviderConfigurationCoordinator
from ClipAI.services.input_resolver import InputResolver
from ClipAI.services.output_actions import OutputActions
from ClipAI.services.paste_target import PasteTargetCoordinator
from ClipAI.services.paste_operation import PasteOperationCoordinator
from ClipAI.services.operation_lifecycle import OperationLifecycleCoordinator
from ClipAI.services.result_router import ResultRouter
from ClipAI.services.shortcut_guide import ShortcutGuideCatalog, ShortcutGuideCoordinator
from ClipAI.services.speech_coordinator import SpeechCoordinator, SpeechVoiceSelector
from ClipAI.services.selection_capture import SelectionCaptureCoordinator
from ClipAI.services.user_control import UserControlCoordinator
from ClipAI.services.voice_input import VoiceInputController
from ClipAI.services.prompt_builder import PromptBuilder
from ClipAI.services.result_processor import ResultProcessor
from ClipAI.ui.result_dialog import ResultDialogPresenter
from ClipAI.ui.tray import TrayController
from ClipAI.app.runtime_personal_styles import PersonalStyleRuntimeModule
from ClipAI.support.logging_setup import configure_logging
from ClipAI.support.diagnostics import SafeDiagnosticsExporter
from ClipAI.support.diagnostics import IncidentReporter
from ClipAI.core.voice import VoiceDisableId, VoiceLanguage, VoiceLanguageChangeId, VoiceSetupId


def _needs_provider_setup(bundle_issues: Sequence[ReadinessIssue]) -> bool:
    return any(issue.feature == "llm" for issue in bundle_issues)


def build_runtime(bundle: ConfigBundle) -> AppRuntime:
    configure_logging(bundle.logging)
    settings_store = DotenvModelPreferenceStore()
    provider_transport = HttpxAsyncTransport()
    provider_execution = ProviderExecutionModule(provider_transport)
    snapshot = build_provider_snapshot(bundle, os.environ, provider_transport)
    provider_backend = AppProviderConfigurationBackend(
        bundle,
        settings_store,
        lambda: dict(os.environ),
        provider_transport,
    )
    provider_configuration = ProviderConfigurationCoordinator(snapshot, provider_backend)
    active_binding = next(item for item in snapshot.bindings if item.provider_id == snapshot.active_provider)
    active_option = next(item for item in snapshot.options if item.provider_id == snapshot.active_provider)
    credential = _credential_for(bundle, snapshot.active_provider)
    provider, model = active_binding.provider, active_binding.model
    readiness_issues = active_binding.readiness_issues
    available_models = active_option.available_models
    clipboard = SystemClipboard()
    speech_available = bundle.tts.enabled and bool(bundle.tts.voice)
    user_preferences = UserPreferencesCoordinator(
        JsonUserPreferencesStore(),
        base_speech_rate=bundle.tts.rate,
        speech_available=speech_available,
    )
    personal_styles = PersonalStyleCoordinator(
        JsonPersonalStyleStore(),
        Utf8PersonalStyleFileReader(),
    )
    runtime_holder: list[AppRuntime] = []
    enqueue = lambda command: runtime_holder[0].enqueue(command)
    voice_controller = VoiceInputController(
        enabled=user_preferences.voice_preferences.enabled,
        language=VoiceLanguage(user_preferences.voice_preferences.language),
    )
    tray = TrayController(
        lambda: runtime_holder[0].enqueue(ShutdownApplication()),
        lambda: runtime_holder[0].enqueue(ExportDiagnostics()),
        lambda: runtime_holder[0].show_last_error(),
        model_selection=ModelSelectionState(snapshot.active_provider, available_models, model),
        provider_selection=ProviderSelectionState(snapshot.options, snapshot.active_provider),
        on_open_provider_settings=lambda: runtime_holder[0].enqueue(OpenProviderSettings()),
        on_open_shortcut_guide=lambda: runtime_holder[0].enqueue(OpenShortcutGuide(uuid.uuid4().hex)),
        on_open_personal_styles=lambda: runtime_holder[0].enqueue(OpenPersonalStyles()),
        guidance_preferences=user_preferences.guidance_preferences,
        on_set_first_use_hints=lambda enabled: runtime_holder[0].enqueue(SetFirstUseHintsEnabled(enabled, uuid.uuid4().hex)),
        on_reset_first_use_hints=lambda: runtime_holder[0].enqueue(ResetFirstUseHints(uuid.uuid4().hex)),
        speech_speed=user_preferences.speech_speed_state,
        on_set_speech_speed=lambda speed: runtime_holder[0].enqueue(SetSpeechSpeed(speed, uuid.uuid4().hex)),
        voice=voice_controller.projection,
        on_enable_voice=lambda: runtime_holder[0].enqueue(OpenVoiceSetup()),
        on_disable_voice=lambda: runtime_holder[0].enqueue(DisableVoiceInput(VoiceDisableId(uuid.uuid4().hex))),
        on_set_voice_language=lambda language: runtime_holder[0].enqueue(SetVoiceLanguage(language)),
        on_manage_voice_permission=lambda: runtime_holder[0].enqueue(OpenVoicePermissionSettings()),
    )
    operation_tracker = OperationLifecycleCoordinator(tray, ready=not readiness_issues)
    native_window_surface = WindowsNativeWindowSurface()
    view = ResultDialogPresenter(
        display_metrics=WindowsDisplayMetricsReader(),
        pointer_press_reader=WindowsPointerPressReader(),
        native_window_surface=native_window_surface,
        focus_transition_diagnostics=bundle.logging.diagnostics.enabled("focus_transitions"),
        voice_projection=voice_controller.projection,
    )
    diagnostics_exporter = SafeDiagnosticsExporter(
        metadata={
            "version": _application_version(),
            "schema_versions": {
                "config": bundle.schema_versions.app,
                "actions": bundle.schema_versions.actions,
                "shortcuts": bundle.schema_versions.shortcuts,
                "output_profiles": bundle.schema_versions.output_profiles,
            },
            "provider": snapshot.active_provider,
            "model": model,
            "ready": not readiness_issues,
            "readiness_codes": [issue.code for issue in readiness_issues],
            "tts_enabled": bundle.tts.enabled,
            "voice_input_backend": bundle.voice_input.backend,
            "logging_enabled": bundle.logging.enabled,
        },
        log_path=bundle.logging.file_path,
        sensitive_values=((credential.value,) if credential and credential.value else ()),
    )
    speech = (
        EdgeSpeechOutput(voice=bundle.tts.voice, rate=bundle.tts.rate, volume=bundle.tts.volume)
        if speech_available
        else None
    )
    clipboard_transactions = ClipboardTransactionCoordinator(clipboard)
    selection_reader = SelectionCaptureCoordinator(
        clipboard_transactions,
        SystemSelectionCaptureAdapter(),
    )
    voice_selector = SpeechVoiceSelector(
        bundle.tts.english_voice,
        japanese_voice=bundle.tts.japanese_voice,
    )
    speech_coordinator = (
        SpeechCoordinator(
            clipboard=clipboard,
            selection_reader=selection_reader,
            speech=speech,
            voice_selector=voice_selector,
            operation_tracker=operation_tracker,
            speech_rate=user_preferences.current_speech_rate,
        )
        if speech is not None
        else None
    )
    output_actions = OutputActions(
        clipboard=clipboard_transactions,
        archive=JsonlArchiveStore(),
    )
    paste_operations = PasteOperationCoordinator(
        clipboard_transactions=clipboard_transactions,
        dispatcher=SystemKeyboardOutput(),
        completion_sink=enqueue,
    )
    paste_targets = PasteTargetCoordinator(view)
    supervisor = TaskSupervisor(bundle.runtime.maintenance_workers)
    input_resolver = InputResolver(clipboard, selection_reader)
    execute_action = ActionExecutor(
        input_resolver=input_resolver,
        prompt_builder=PromptBuilder(bundle.app.system_prompt, bundle.output_profiles),
        result_processor=ResultProcessor(bundle.output_profiles),
        default_temperature=bundle.app.temperature,
        available_actions=("copy", "paste", "archive", "follow_up", "speaker") if speech is not None else ("copy", "paste", "archive", "follow_up"),
        operation_tracker=operation_tracker,
        result_router=ResultRouter(
            SupervisedSpeechResultSink(speech_coordinator, supervisor)
            if speech_coordinator is not None
            else None
        ),
        guidance_preferences=user_preferences,
        blocking_runner=lambda task_id, work: supervisor.run(
            task_id,
            work,
            task_class="interactive",
        ),
    )

    def register(
        shortcut_map: dict[str, dict[str, str]],
        callback: Callable[[ShortcutInputEvent], None],
    ) -> ShortcutInput:
        return register_hotkeys_with_long_press(
            shortcut_map,
            callback,
            modifier_mode=bundle.app.modifier_mode,
            diagnostics_enabled=bundle.logging.diagnostics.enabled,
            entry_panel_enabled=bundle.app.entry_panel_enabled,
        )

    user_control = UserControlCoordinator()
    incident_reporter = IncidentReporter()
    workflow_module = WorkflowRuntimeModule(
        actions=bundle.actions,
        shortcuts=bundle.shortcuts,
        execute_action=execute_action,
        view=view,
        provider_execution=provider_execution,
        enqueue=enqueue,
        provider_configuration=provider_configuration,
        workflow_context_reader=view,
        voice_capture_context_reader=view,
        incident_reporter=incident_reporter,
        operation_tracker=operation_tracker,
        notifier=tray,
        speech_coordinator=speech_coordinator,
        user_control=user_control,
        attention_presenter=view,
        personal_styles=personal_styles,
        input_resolver=input_resolver,
        supervisor=supervisor,
    )
    result_output_module = ResultOutputRuntimeModule(
        output_actions=output_actions,
        paste_operations=paste_operations,
        supervisor=supervisor,
        workflow_controller=workflow_module.controller_for,
        output_operation_presenter=view,
        incident_reporter=incident_reporter,
        operation_tracker=operation_tracker,
        diagnostics_exporter=diagnostics_exporter,
        notifier=tray,
        speech_coordinator=speech_coordinator,
        paste_targets=paste_targets,
        user_control=user_control,
    )
    provider_configuration_module = ProviderConfigurationRuntimeModule(
        coordinator=provider_configuration,
        provider_execution=provider_execution,
        enqueue=enqueue,
        operation_tracker=operation_tracker,
        model_selection_presenter=tray,
        provider_selection_presenter=tray,
        provider_settings_presenter=view,
        user_control=user_control,
    )
    action_feedback_module = ActionFeedbackRuntimeModule(
        supervisor=supervisor,
        workflow_controller=workflow_module.controller_for,
        enqueue=enqueue,
        action_feedback=ActionFeedbackService(JsonlActionFeedbackStore()),
    )
    user_preferences_module = UserPreferencesRuntimeModule(
        supervisor=supervisor,
        enqueue=enqueue,
        user_preferences=user_preferences,
        guidance_preferences_presenter=tray,
        speech_speed_presenter=tray,
        operation_tracker=operation_tracker,
        notifier=tray,
    )
    personal_styles_module = PersonalStyleRuntimeModule(
        coordinator=personal_styles,
        supervisor=supervisor,
        enqueue=enqueue,
        presenter=view,
        operation_tracker=operation_tracker,
    )
    local_app_data = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    owned_processes = AppOwnedProcessRegistry()
    voice_engine = BrowserSpeechWebView2Engine(
        lambda event: enqueue(VoiceEngineEventReceived(event)),
        profile_root=local_app_data,
        on_process_started=owned_processes.register,
        on_process_stopped=owned_processes.unregister,
    )
    foreground_monitor = WindowsForegroundWindowMonitor(
        lambda target: runtime_holder[0].enqueue(ExternalForegroundChanged(target)),
        is_owned_process=owned_processes.contains,
    )

    def project_voice(projection) -> None:
        tray.set_voice_projection(projection)
        view.set_voice_projection(projection)

    voice_input_module = VoiceInputRuntimeModule(
        controller=voice_controller,
        engine=voice_engine,
        workflows=workflow_module,
        paste_target_reader=lambda: result_output_module.current_paste_target,
        capture_external_target=foreground_monitor.capture_foreground_target,
        persist_enabled=lambda setup_id: user_preferences_module.begin_voice_enabled(
            True,
            setup_id,
            lambda error: VoicePreferenceSaved(VoiceSetupId(setup_id), error),
        ),
        persist_disabled=lambda disable_id: user_preferences_module.begin_voice_enabled(
            False,
            disable_id,
            lambda error: VoiceDisablePreferenceSaved(VoiceDisableId(disable_id), error),
        ),
        persist_language=lambda operation_id, language: user_preferences_module.begin_voice_language(
            language,
            operation_id,
            lambda error: VoiceLanguagePreferenceSaved(VoiceLanguageChangeId(operation_id), error),
        ),
        complete_voice_preference=user_preferences_module.complete_voice_enabled,
        dispatch=enqueue,
        projection_sink=project_voice,
        notifier=tray,
        setup_presenter=view,
        focused_surface_reader=lambda: user_control.focused_surface,
        open_permission_settings=open_microphone_privacy_settings,
    )
    shortcut_guide_module = ShortcutGuideRuntimeModule(
        catalog=ShortcutGuideCatalog(
            bundle.shortcuts,
            bundle.actions,
            modifier_mode=bundle.app.modifier_mode,
        ),
        coordinator=ShortcutGuideCoordinator(),
        presenter=view,
    )
    runtime = AppRuntime(
        shortcuts=bundle.shortcuts,
        view=view,
        supervisor=supervisor,
        provider_execution=provider_execution,
        workflows=workflow_module,
        result_output=result_output_module,
        provider_configuration=provider_configuration_module,
        action_feedback=action_feedback_module,
        user_preferences=user_preferences_module,
        hotkey_registrar=register,
        tray_factory=lambda _on_exit: tray,
        operation_tracker=operation_tracker,
        shortcut_guide=shortcut_guide_module,
        foreground_monitor=foreground_monitor,
        user_control=user_control,
        voice_input=voice_input_module,
        personal_styles=personal_styles_module,
    )
    runtime_holder.append(runtime)
    if _needs_provider_setup(readiness_issues):
        runtime.enqueue(OpenProviderSettings(snapshot.active_provider))
    return runtime


def _build_provider(
    bundle: ConfigBundle,
    credential: ProviderCredential | None = None,
    transport: HttpTransport | None = None,
) -> tuple[LLMProvider, str]:
    active = bundle.providers.active
    if active == "fake":
        return FakeProvider(), "fake-model"
    settings = bundle.providers.active_settings()
    assert settings is not None
    model = _resolve_active_model(bundle)
    credential = credential or ProviderCredential(settings.api_key_env)
    transport = transport or HttpxAsyncTransport()
    if active == "gemini":
        return GeminiProvider(bundle.providers.gemini, credential, transport), model
    if active == "openai":
        return OpenAIProvider(bundle.providers.openai, credential, transport), model
    if active == "anthropic":
        return AnthropicProvider(bundle.providers.anthropic, credential, transport), model
    if active == "gateway":
        return OpenAICompatibleGatewayProvider(bundle.providers.gateway, credential, transport), model
    raise ValueError(f"unsupported provider: {active}")


def _build_provider_snapshot(bundle: ConfigBundle, environment=None) -> ProviderRuntimeSnapshot:
    return build_provider_snapshot(
        bundle,
        os.environ if environment is None else environment,
        HttpxAsyncTransport(),
    )


def _credential_for(bundle: ConfigBundle, provider_id: str) -> ProviderCredential | None:
    if provider_id == "fake":
        return None
    settings = getattr(bundle.providers, provider_id)
    return ProviderCredential(settings.api_key_env, os.getenv(settings.api_key_env))


def _resolve_active_credential(bundle: ConfigBundle) -> ProviderCredential | None:
    settings = bundle.providers.active_settings()
    if settings is None:
        return None
    return ProviderCredential(settings.api_key_env, os.getenv(settings.api_key_env))


def _resolve_active_model(bundle: ConfigBundle) -> str:
    settings = bundle.providers.active_settings()
    if settings is None:
        return "fake-model"
    env_name = f"{bundle.providers.active.upper()}_MODEL"
    model = (os.getenv(env_name) or settings.model).strip()
    if not model:
        raise ConfigError(f"{env_name} must be a non-empty model name")
    return model


def _application_version() -> str:
    try:
        return version("clipai")
    except PackageNotFoundError:
        return "development"
