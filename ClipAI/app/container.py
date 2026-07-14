from __future__ import annotations

from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version
import os

from ClipAI.app.config_schema import ConfigBundle
from ClipAI.core.errors import ConfigError
from ClipAI.app.readiness import assess_provider_readiness
from ClipAI.app.runtime import AppRuntime
from ClipAI.core.commands import ExportDiagnostics, OpenProviderSettings, ReloadConfiguration, SelectProvider, SelectProviderModel, ShutdownApplication
from ClipAI.core.models import ModelSelectionState, ProviderOption, ProviderSelectionState, ReadinessIssue
from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.ports import LLMProvider
from ClipAI.platform.clipboard import SystemClipboard
from ClipAI.platform.hotkey import register_hotkeys_with_long_press
from ClipAI.platform.selection import SystemSelectionReader
from ClipAI.platform.filesystem import JsonlArchiveStore
from ClipAI.platform.dotenv_preferences import DotenvModelPreferenceStore
from ClipAI.platform.display import WindowsDisplayMetricsReader
from ClipAI.platform.speech import EdgeSpeechOutput
from ClipAI.platform.keyboard import SystemKeyboardOutput
from ClipAI.platform.notification import SystemNotifier
from ClipAI.providers.fake import FakeProvider
from ClipAI.providers.gateway import OpenAICompatibleGatewayProvider, normalize_gateway_base_url
from ClipAI.providers.anthropic import AnthropicProvider
from ClipAI.providers.gemini import GeminiProvider
from ClipAI.providers.openai import OpenAIProvider
from ClipAI.providers.model_catalog import ProviderModelCatalogClient
from ClipAI.providers.settings import ProviderCredential
from ClipAI.providers.settings import GatewaySettings
from ClipAI.services.execute_action import ActionExecutor
from ClipAI.services.provider_binding import ProviderExecutionBinding, ProviderRuntimeSnapshot
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


def build_runtime(bundle: ConfigBundle) -> AppRuntime:
    configure_logging(bundle.logging)
    settings_store = DotenvModelPreferenceStore()
    snapshot = _build_provider_snapshot(bundle)
    active_binding = next(item for item in snapshot.bindings if item.provider_id == snapshot.active_provider)
    active_option = next(item for item in snapshot.options if item.provider_id == snapshot.active_provider)
    credential = _credential_for(bundle, snapshot.active_provider)
    provider, model = active_binding.provider, active_binding.model
    readiness_issues = active_binding.readiness_issues
    available_models = active_option.available_models
    clipboard = SystemClipboard()
    runtime_holder: list[AppRuntime] = []
    tray = TrayController(
        lambda: runtime_holder[0].enqueue(ShutdownApplication()),
        lambda: runtime_holder[0].enqueue(ExportDiagnostics()),
        lambda: runtime_holder[0].show_last_error(),
        model_selection=ModelSelectionState(snapshot.active_provider, available_models, model),
        on_select_model=lambda provider_name, selected_model: runtime_holder[0].enqueue(SelectProviderModel(provider_name, selected_model)),
        provider_selection=ProviderSelectionState(snapshot.options, snapshot.active_provider),
        on_select_provider=lambda provider_name: runtime_holder[0].enqueue(SelectProvider(provider_name)),
        on_reload_configuration=lambda: runtime_holder[0].enqueue(ReloadConfiguration()),
        on_open_provider_settings=lambda: runtime_holder[0].enqueue(OpenProviderSettings()),
    )
    operation_tracker = OperationLifecycleCoordinator(tray, ready=not readiness_issues)
    view = ResultDialogPresenter(display_metrics=WindowsDisplayMetricsReader())
    notifier = SystemNotifier()
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
    voice_selector = SpeechVoiceSelector(bundle.tts.english_voice)
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
    model_catalog_client = ProviderModelCatalogClient()

    def validate_provider_credential(provider_id: str, api_key: str, base_url: str, model: str) -> None:
        settings = (
            GatewaySettings("Custom Gateway", normalize_gateway_base_url(base_url), model, bundle.providers.gateway.timeout_sec, available_models=(model,))
            if provider_id == "gateway"
            else getattr(bundle.providers, provider_id)
        )
        model_catalog_client.list_models(provider_id, settings, api_key)

    def build_provider_candidate(provider_id: str, selected_model: str, api_key: str, server_name: str, base_url: str) -> ProviderRuntimeSnapshot:
        settings = getattr(bundle.providers, provider_id)
        environment = {
            **os.environ,
            **settings_store.read_settings(),
            "CLIPAI_PROVIDER": provider_id,
            settings.api_key_env: api_key,
            f"{provider_id.upper()}_MODEL": selected_model,
        }
        if provider_id == "gateway":
            environment.update(
                {
                    "CLIPAI_GATEWAY_NAME": server_name,
                    "CLIPAI_GATEWAY_BASE_URL": base_url,
                    "CLIPAI_GATEWAY_API_KEY": api_key,
                    "CLIPAI_GATEWAY_MODEL": selected_model,
                }
            )
        return _build_provider_snapshot(bundle, environment)

    execute_action = ActionExecutor(
        input_resolver=InputResolver(clipboard, selection_reader),
        prompt_builder=PromptBuilder(bundle.app.system_prompt, bundle.output_profiles),
        result_processor=ResultProcessor(bundle.output_profiles),
        default_temperature=bundle.app.temperature,
        available_actions=("copy", "paste", "archive", "follow_up", "speaker") if speech is not None else ("copy", "paste", "archive", "follow_up"),
        operation_tracker=operation_tracker,
        result_router=ResultRouter(speech_coordinator),
    )

    def register(action_map: dict[str, dict[str, str]], callback: Callable[[str, str], None]) -> object:
        return register_hotkeys_with_long_press(
            action_map,
            callback,  # type: ignore[arg-type]
            modifier_mode=bundle.app.modifier_mode,
            diagnostics_enabled=bundle.logging.diagnostics.enabled,
        )

    runtime = AppRuntime(
        actions=bundle.actions,
        shortcuts=bundle.shortcuts,
        execute_action=execute_action,
        output_actions=output_actions,
        view=view,
        supervisor=TaskSupervisor(bundle.runtime.max_workers),
        provider_binding=active_binding,
        hotkey_registrar=register,
        tray_factory=lambda _on_exit: tray,
        operation_tracker=operation_tracker,
        diagnostics_exporter=diagnostics_exporter,
        notifier=notifier,
        speech_coordinator=speech_coordinator,
        workflow_context_reader=view,
        output_operation_presenter=view,
        available_models=available_models,
        settings_store=settings_store,
        model_selection_presenter=tray,
        provider_options=snapshot.options,
        provider_bindings=snapshot.bindings,
        provider_selection_presenter=tray,
        reload_provider_settings=lambda: _build_provider_snapshot(bundle, {**os.environ, **settings_store.read_settings()}),
        provider_settings_presenter=view,
        validate_provider_credential=validate_provider_credential,
        build_provider_candidate=build_provider_candidate,
        gateway_name=snapshot.gateway_name,
        gateway_base_url=snapshot.gateway_base_url,
    )
    runtime_holder.append(runtime)
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
    values = os.environ if environment is None else environment
    active = (values.get("CLIPAI_PROVIDER") or bundle.providers.active).strip().lower()
    allowed = ("gemini", "openai", "anthropic", "gateway")
    if active == "fake":
        binding = ProviderExecutionBinding(FakeProvider(), "fake", "fake-model")
        option = ProviderOption("fake", "Fake", ("fake-model",), "fake-model", True)
        return ProviderRuntimeSnapshot("fake", (binding,), (option,))
    if active not in allowed:
        raise ConfigError(f"CLIPAI_PROVIDER must be one of: {', '.join(allowed)}")
    bindings: list[ProviderExecutionBinding] = []
    options: list[ProviderOption] = []
    display_names = {"gemini": "Gemini", "openai": "OpenAI", "anthropic": "Anthropic"}
    provider_types = {"gemini": GeminiProvider, "openai": OpenAIProvider, "anthropic": AnthropicProvider}
    for provider_id in ("gemini", "openai", "anthropic"):
        settings = getattr(bundle.providers, provider_id)
        credential = ProviderCredential(settings.api_key_env, values.get(settings.api_key_env))
        model = (values.get(f"{provider_id.upper()}_MODEL") or settings.model).strip()
        available_models = settings.available_models or (settings.model,)
        if model not in available_models:
            raise ConfigError(f"{provider_id.upper()}_MODEL must be one of: {', '.join(available_models)}")
        issues = () if credential.value else (
            ReadinessIssue(
                "provider.missing_api_key",
                f"Set {settings.api_key_env} and reload ClipAI to use {provider_id}.",
                "llm",
            ),
        )
        provider = provider_types[provider_id](settings, credential)
        bindings.append(ProviderExecutionBinding(provider, provider_id, model, issues))
        options.append(ProviderOption(provider_id, display_names[provider_id], available_models, model, not issues))
    gateway_defaults = bundle.providers.gateway
    gateway_name = (values.get("CLIPAI_GATEWAY_NAME") or gateway_defaults.name or "Custom Gateway").strip()
    gateway_base_url = (values.get("CLIPAI_GATEWAY_BASE_URL") or gateway_defaults.base_url).strip()
    gateway_model = (values.get("CLIPAI_GATEWAY_MODEL") or gateway_defaults.model).strip()
    gateway_key = values.get("CLIPAI_GATEWAY_API_KEY") or ""
    gateway_ready = bool(gateway_base_url and gateway_model)
    if gateway_ready:
        gateway_base_url = normalize_gateway_base_url(gateway_base_url)
    elif active == "gateway":
        raise ConfigError("CLIPAI_GATEWAY_BASE_URL and CLIPAI_GATEWAY_MODEL are required when CLIPAI_PROVIDER=gateway")
    gateway_settings = GatewaySettings(
        gateway_name or "Custom Gateway",
        gateway_base_url,
        gateway_model,
        gateway_defaults.timeout_sec,
        available_models=(gateway_model,) if gateway_model else (),
    )
    gateway_issues = () if gateway_ready else (
        ReadinessIssue("provider.gateway_not_configured", "Configure the custom gateway before selecting it.", "llm"),
    )
    bindings.append(
        ProviderExecutionBinding(
            OpenAICompatibleGatewayProvider(gateway_settings, ProviderCredential("CLIPAI_GATEWAY_API_KEY", gateway_key)),
            "gateway",
            gateway_model,
            gateway_issues,
        )
    )
    options.append(ProviderOption("gateway", gateway_name or "Custom Gateway", (gateway_model,) if gateway_model else (), gateway_model, gateway_ready))
    return ProviderRuntimeSnapshot(active, tuple(bindings), tuple(options), gateway_name or "Custom Gateway", gateway_base_url)


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
    available_models = settings.available_models or (settings.model,)
    if model not in available_models:
        raise ConfigError(f"{env_name} must be one of: {', '.join(available_models)}")
    return model


def _application_version() -> str:
    try:
        return version("clipai")
    except PackageNotFoundError:
        return "development"
