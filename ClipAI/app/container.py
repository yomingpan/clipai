from __future__ import annotations

from collections.abc import Callable, Sequence
from importlib.metadata import PackageNotFoundError, version
import os
import uuid

from ClipAI.app.config_schema import ConfigBundle
from ClipAI.core.errors import ConfigError
from ClipAI.app.provider_configuration import AppProviderConfigurationBackend, build_provider_snapshot
from ClipAI.app.readiness import assess_provider_readiness
from ClipAI.app.runtime import AppRuntime
from ClipAI.app.runtime_outputs import ResultOutputRuntimeModule
from ClipAI.app.runtime_provider_configuration import ProviderConfigurationRuntimeModule
from ClipAI.app.runtime_user_persistence import UserPersistenceRuntimeModule
from ClipAI.app.runtime_workflows import WorkflowRuntimeModule
from ClipAI.core.commands import ExportDiagnostics, OpenProviderSettings, ResetFirstUseHints, SetFirstUseHintsEnabled, ShutdownApplication
from ClipAI.core.models import HotkeyEventType, ModelSelectionState, ProviderSelectionState, ReadinessIssue
from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.ports import LLMProvider, Stoppable
from ClipAI.platform.clipboard import SystemClipboard
from ClipAI.platform.action_feedback import JsonlActionFeedbackStore
from ClipAI.platform.guidance_preferences import JsonGuidancePreferencesStore
from ClipAI.platform.hotkey import register_hotkeys_with_long_press
from ClipAI.platform.selection import SystemSelectionReader
from ClipAI.platform.filesystem import JsonlArchiveStore
from ClipAI.platform.dotenv_preferences import DotenvModelPreferenceStore
from ClipAI.platform.display import WindowsDisplayMetricsReader
from ClipAI.platform.speech import EdgeSpeechOutput
from ClipAI.platform.keyboard import SystemKeyboardOutput
from ClipAI.providers.fake import FakeProvider
from ClipAI.providers.gateway import OpenAICompatibleGatewayProvider
from ClipAI.providers.anthropic import AnthropicProvider
from ClipAI.providers.gemini import GeminiProvider
from ClipAI.providers.openai import OpenAIProvider
from ClipAI.providers.settings import ProviderCredential
from ClipAI.services.execute_action import ActionExecutor
from ClipAI.services.action_feedback import ActionFeedbackService
from ClipAI.services.guidance_preferences import GuidancePreferencesCoordinator
from ClipAI.services.provider_binding import ProviderRuntimeSnapshot
from ClipAI.services.provider_configuration import ProviderConfigurationCoordinator
from ClipAI.services.input_resolver import InputResolver
from ClipAI.services.output_actions import OutputActions
from ClipAI.services.operation_lifecycle import OperationLifecycleCoordinator
from ClipAI.services.result_router import ResultRouter
from ClipAI.services.speech_coordinator import SpeechCoordinator, SpeechVoiceSelector
from ClipAI.services.prompt_builder import PromptBuilder
from ClipAI.services.result_processor import ResultProcessor
from ClipAI.ui.result_dialog import ResultDialogPresenter
from ClipAI.ui.tray import TrayController
from ClipAI.support.logging_setup import configure_logging
from ClipAI.support.diagnostics import SafeDiagnosticsExporter
from ClipAI.support.diagnostics import IncidentReporter


def _needs_provider_setup(bundle_issues: Sequence[ReadinessIssue]) -> bool:
    return any(issue.code == "provider.missing_api_key" for issue in bundle_issues)


def build_runtime(bundle: ConfigBundle) -> AppRuntime:
    configure_logging(bundle.logging)
    settings_store = DotenvModelPreferenceStore()
    snapshot = build_provider_snapshot(bundle, os.environ)
    provider_backend = AppProviderConfigurationBackend(bundle, settings_store, lambda: dict(os.environ))
    provider_configuration = ProviderConfigurationCoordinator(snapshot, provider_backend)
    active_binding = next(item for item in snapshot.bindings if item.provider_id == snapshot.active_provider)
    active_option = next(item for item in snapshot.options if item.provider_id == snapshot.active_provider)
    credential = _credential_for(bundle, snapshot.active_provider)
    provider, model = active_binding.provider, active_binding.model
    readiness_issues = active_binding.readiness_issues
    available_models = active_option.available_models
    clipboard = SystemClipboard()
    guidance_preferences = GuidancePreferencesCoordinator(JsonGuidancePreferencesStore())
    runtime_holder: list[AppRuntime] = []
    tray = TrayController(
        lambda: runtime_holder[0].enqueue(ShutdownApplication()),
        lambda: runtime_holder[0].enqueue(ExportDiagnostics()),
        lambda: runtime_holder[0].show_last_error(),
        model_selection=ModelSelectionState(snapshot.active_provider, available_models, model),
        provider_selection=ProviderSelectionState(snapshot.options, snapshot.active_provider),
        on_open_provider_settings=lambda: runtime_holder[0].enqueue(OpenProviderSettings()),
        guidance_preferences=guidance_preferences.preferences,
        on_set_first_use_hints=lambda enabled: runtime_holder[0].enqueue(SetFirstUseHintsEnabled(enabled, uuid.uuid4().hex)),
        on_reset_first_use_hints=lambda: runtime_holder[0].enqueue(ResetFirstUseHints(uuid.uuid4().hex)),
    )
    operation_tracker = OperationLifecycleCoordinator(tray, ready=not readiness_issues)
    view = ResultDialogPresenter(display_metrics=WindowsDisplayMetricsReader())
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
        if bundle.tts.enabled and bundle.tts.voice
        else None
    )
    selection_reader = SystemSelectionReader(clipboard)
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
        )
        if speech is not None
        else None
    )
    output_actions = OutputActions(
        clipboard=clipboard,
        archive=JsonlArchiveStore(),
        keyboard=SystemKeyboardOutput(),
    )
    execute_action = ActionExecutor(
        input_resolver=InputResolver(clipboard, selection_reader),
        prompt_builder=PromptBuilder(bundle.app.system_prompt, bundle.output_profiles),
        result_processor=ResultProcessor(bundle.output_profiles),
        default_temperature=bundle.app.temperature,
        available_actions=("copy", "paste", "archive", "follow_up", "speaker") if speech is not None else ("copy", "paste", "archive", "follow_up"),
        operation_tracker=operation_tracker,
        result_router=ResultRouter(speech_coordinator),
        guidance_preferences=guidance_preferences,
    )

    def register(action_map: dict[str, dict[str, str]], callback: Callable[[str, HotkeyEventType], None]) -> Stoppable:
        return register_hotkeys_with_long_press(
            action_map,
            callback,
            modifier_mode=bundle.app.modifier_mode,
            diagnostics_enabled=bundle.logging.diagnostics.enabled,
        )

    supervisor = TaskSupervisor(bundle.runtime.max_workers)
    incident_reporter = IncidentReporter()
    enqueue = lambda command: runtime_holder[0].enqueue(command)
    workflow_module = WorkflowRuntimeModule(
        actions=bundle.actions,
        shortcuts=bundle.shortcuts,
        execute_action=execute_action,
        view=view,
        supervisor=supervisor,
        enqueue=enqueue,
        provider_configuration=provider_configuration,
        workflow_context_reader=view,
        incident_reporter=incident_reporter,
        operation_tracker=operation_tracker,
        notifier=tray,
        speech_coordinator=speech_coordinator,
    )
    result_output_module = ResultOutputRuntimeModule(
        output_actions=output_actions,
        supervisor=supervisor,
        workflow_controller=workflow_module.controller_for,
        has_foreground_workflow=workflow_module.has_foreground_workflow,
        output_operation_presenter=view,
        enqueue=enqueue,
        incident_reporter=incident_reporter,
        operation_tracker=operation_tracker,
        diagnostics_exporter=diagnostics_exporter,
        notifier=tray,
        speech_coordinator=speech_coordinator,
    )
    provider_configuration_module = ProviderConfigurationRuntimeModule(
        coordinator=provider_configuration,
        supervisor=supervisor,
        enqueue=enqueue,
        operation_tracker=operation_tracker,
        model_selection_presenter=tray,
        provider_selection_presenter=tray,
        provider_settings_presenter=view,
    )
    user_persistence_module = UserPersistenceRuntimeModule(
        supervisor=supervisor,
        workflow_controller=workflow_module.controller_for,
        enqueue=enqueue,
        action_feedback=ActionFeedbackService(JsonlActionFeedbackStore()),
        guidance_preferences=guidance_preferences,
        guidance_preferences_presenter=tray,
        notifier=tray,
    )
    runtime = AppRuntime(
        shortcuts=bundle.shortcuts,
        view=view,
        supervisor=supervisor,
        workflows=workflow_module,
        result_output=result_output_module,
        provider_configuration=provider_configuration_module,
        user_persistence=user_persistence_module,
        hotkey_registrar=register,
        tray_factory=lambda _on_exit: tray,
        operation_tracker=operation_tracker,
    )
    runtime_holder.append(runtime)
    if _needs_provider_setup(readiness_issues):
        runtime.enqueue(OpenProviderSettings(snapshot.active_provider))
    return runtime


def _build_provider(bundle: ConfigBundle, credential: ProviderCredential | None = None) -> tuple[LLMProvider, str]:
    active = bundle.providers.active
    if active == "fake":
        return FakeProvider(), "fake-model"
    settings = bundle.providers.active_settings()
    assert settings is not None
    model = _resolve_active_model(bundle)
    credential = credential or ProviderCredential(settings.api_key_env)
    if active == "gemini":
        return GeminiProvider(bundle.providers.gemini, credential), model
    if active == "openai":
        return OpenAIProvider(bundle.providers.openai, credential), model
    if active == "anthropic":
        return AnthropicProvider(bundle.providers.anthropic, credential), model
    if active == "gateway":
        return OpenAICompatibleGatewayProvider(bundle.providers.gateway, credential), model
    raise ValueError(f"unsupported provider: {active}")


def _build_provider_snapshot(bundle: ConfigBundle, environment=None) -> ProviderRuntimeSnapshot:
    return build_provider_snapshot(bundle, os.environ if environment is None else environment)


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
