from __future__ import annotations

from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version
import os

from ClipAI.app.config_schema import ConfigBundle
from ClipAI.app.readiness import assess_provider_readiness
from ClipAI.app.runtime import AppRuntime
from ClipAI.core.commands import ExportDiagnostics, ShutdownApplication
from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.ports import LLMProvider
from ClipAI.platform.clipboard import SystemClipboard
from ClipAI.platform.hotkey import register_hotkeys_with_long_press
from ClipAI.platform.selection import SystemSelectionReader
from ClipAI.platform.filesystem import JsonlArchiveStore
from ClipAI.platform.display import WindowsDisplayMetricsReader
from ClipAI.platform.speech import EdgeSpeechOutput
from ClipAI.platform.keyboard import SystemKeyboardOutput
from ClipAI.platform.notification import SystemNotifier
from ClipAI.providers.fake import FakeProvider
from ClipAI.providers.anthropic import AnthropicProvider
from ClipAI.providers.gemini import GeminiProvider
from ClipAI.providers.openai import OpenAIProvider
from ClipAI.providers.settings import ProviderCredential
from ClipAI.services.execute_action import ActionExecutor
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
    credential = _resolve_active_credential(bundle)
    readiness_issues = assess_provider_readiness(bundle.providers, credential)
    provider, model = _build_provider(bundle, credential)
    clipboard = SystemClipboard()
    runtime_holder: list[AppRuntime] = []
    tray = TrayController(
        lambda: runtime_holder[0].enqueue(ShutdownApplication()),
        lambda: runtime_holder[0].enqueue(ExportDiagnostics()),
        lambda: runtime_holder[0].show_last_error(),
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
            "provider": bundle.providers.active,
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
    output_actions = OutputActions(
        clipboard=clipboard,
        archive=JsonlArchiveStore(),
        speech=speech,
        keyboard=SystemKeyboardOutput(),
    )

    def speak_result(text: str) -> None:
        operation = operation_tracker.start(f"tts:sequence:{os.urandom(8).hex()}", "tts")
        try:
            output_actions.speak(text)
        except BaseException:
            operation.fail()
            raise
        operation.succeed()

    execute_action = ActionExecutor(
        input_resolver=InputResolver(clipboard, selection_reader),
        provider=provider,
        prompt_builder=PromptBuilder(bundle.app.system_prompt, bundle.output_profiles),
        result_processor=ResultProcessor(bundle.output_profiles),
        model=model,
        default_temperature=bundle.app.temperature,
        provider_name=bundle.providers.active,
        available_actions=("copy", "paste", "archive", "follow_up", "speaker") if speech is not None else ("copy", "paste", "archive", "follow_up"),
        operation_tracker=operation_tracker,
        readiness_issues=readiness_issues,
        result_router=ResultRouter(speak_result if speech is not None else None),
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
        model=model,
        hotkey_registrar=register,
        tray_factory=lambda _on_exit: tray,
        operation_tracker=operation_tracker,
        diagnostics_exporter=diagnostics_exporter,
        notifier=notifier,
        speech_coordinator=(
            SpeechCoordinator(
                clipboard=clipboard,
                selection_reader=selection_reader,
                speech=speech,
                voice_selector=SpeechVoiceSelector(bundle.tts.english_voice),
                operation_tracker=operation_tracker,
            )
            if speech is not None
            else None
        ),
    )
    runtime_holder.append(runtime)
    return runtime


def _build_provider(bundle: ConfigBundle, credential: ProviderCredential | None = None) -> tuple[LLMProvider, str]:
    active = bundle.providers.active
    if active == "fake":
        return FakeProvider(), "fake-model"
    settings = bundle.providers.active_settings()
    assert settings is not None
    credential = credential or ProviderCredential(settings.api_key_env)
    if active == "gemini":
        return GeminiProvider(bundle.providers.gemini, credential), bundle.providers.gemini.model
    if active == "openai":
        return OpenAIProvider(bundle.providers.openai, credential), bundle.providers.openai.model
    if active == "anthropic":
        return AnthropicProvider(bundle.providers.anthropic, credential), bundle.providers.anthropic.model
    raise ValueError(f"unsupported provider: {active}")


def _resolve_active_credential(bundle: ConfigBundle) -> ProviderCredential | None:
    settings = bundle.providers.active_settings()
    if settings is None:
        return None
    return ProviderCredential(settings.api_key_env, os.getenv(settings.api_key_env))


def _application_version() -> str:
    try:
        return version("clipai")
    except PackageNotFoundError:
        return "development"
