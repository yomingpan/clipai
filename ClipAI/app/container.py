from __future__ import annotations

from collections.abc import Callable

from ClipAI.app.config_schema import ConfigBundle
from ClipAI.app.runtime import AppRuntime
from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.ports import LLMProvider
from ClipAI.platform.clipboard import SystemClipboard
from ClipAI.platform.hotkey import register_hotkeys_with_long_press
from ClipAI.platform.selection import NoopSelectionReader
from ClipAI.providers.fake import FakeProvider
from ClipAI.providers.anthropic import AnthropicProvider
from ClipAI.providers.gemini import GeminiProvider
from ClipAI.providers.openai import OpenAIProvider
from ClipAI.services.execute_action import ExecuteAction
from ClipAI.services.input_resolver import InputResolver
from ClipAI.services.output_actions import OutputActions
from ClipAI.services.prompt_builder import PromptBuilder
from ClipAI.services.result_processor import ResultProcessor
from ClipAI.ui.result_dialog import ResultDialogPresenter
from ClipAI.support.logging_setup import configure_logging


def build_runtime(bundle: ConfigBundle) -> AppRuntime:
    configure_logging(bundle.logging)
    provider, model = _build_provider(bundle)
    clipboard = SystemClipboard()
    view = ResultDialogPresenter()
    execute_action = ExecuteAction(
        input_resolver=InputResolver(clipboard, NoopSelectionReader()),
        provider=provider,
        prompt_builder=PromptBuilder(),
        result_processor=ResultProcessor(),
        model=model,
        default_temperature=bundle.app.temperature,
        provider_name=bundle.providers.active,
    )

    def register(action_map: dict[str, dict[str, str]], callback: Callable[[str, str], None]) -> object:
        return register_hotkeys_with_long_press(
            action_map,
            callback,  # type: ignore[arg-type]
            modifier_mode=bundle.app.modifier_mode,
            diagnostics_enabled=bundle.logging.diagnostics.enabled,
        )

    return AppRuntime(
        actions=bundle.actions,
        execute_action=execute_action,
        output_actions=OutputActions(clipboard=clipboard),
        view=view,
        supervisor=TaskSupervisor(bundle.runtime.max_workers),
        model=model,
        hotkey_registrar=register,
    )


def _build_provider(bundle: ConfigBundle) -> tuple[LLMProvider, str]:
    active = bundle.providers.active
    if active == "fake":
        return FakeProvider(), "fake-model"
    settings = bundle.providers.active_settings()
    if active == "gemini":
        return GeminiProvider(bundle.providers.gemini), bundle.providers.gemini.model
    if active == "openai":
        return OpenAIProvider(bundle.providers.openai), bundle.providers.openai.model
    if active == "anthropic":
        return AnthropicProvider(bundle.providers.anthropic), bundle.providers.anthropic.model
    raise ValueError(f"unsupported provider: {active}")
