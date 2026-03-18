from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from clipai.core.cancellation import CancellationController
from clipai.core.constants import EVENT_PIPELINE_UPDATE
from clipai.core.event_bus import EventBus
from clipai.providers.factory import build_provider
from clipai.capabilities.actions.action_registry import AppConfigBundle
from clipai.capabilities.actions.action_service import ActionService, ActionRunResult
from clipai.capabilities.context.input_resolver import InputResolver, InputResolution
from clipai.capabilities.actions.output_applier import OutputApplier, OutputModeError
from clipai.capabilities.actions.resolve_config import resolve_action_config
from clipai.capabilities.context.runtime_context import RuntimeContext


@dataclass(frozen=True)
class RunRequest:
    action_id: str
    explicit_text: str | None = None
    explicit_messages: list[dict[str, str]] | None = None
    model_override: str | None = None
    base_url_override: str | None = None


@dataclass(frozen=True)
class RunOutcome:
    action_id: str
    action_name: str
    input_resolution: InputResolution
    output_mode: str
    result: ActionRunResult


@dataclass(frozen=True)
class RunCallbacks:
    on_input_resolved: Callable[[InputResolution], None] | None = None
    on_chunk: Callable[[str], None] | None = None
    on_complete: Callable[[ActionRunResult], None] | None = None


class ActionRunner:
    def __init__(self, bundle: AppConfigBundle, event_bus: EventBus | None = None) -> None:
        self._bundle = bundle
        self._bus = event_bus or EventBus()

    @property
    def event_bus(self) -> EventBus:
        return self._bus

    @property
    def actions(self) -> list[dict[str, Any]]:
        return self._bundle.actions

    @property
    def action_map(self) -> dict[str, dict[str, Any]]:
        return self._bundle.action_map

    @property
    def provider_config(self) -> dict[str, Any]:
        return dict(self._bundle.provider_cfg)

    def _default_stream_enabled(self, action_def: dict[str, Any]) -> bool:
        return bool(action_def.get("stream", self._bundle.app_cfg.get("stream", True)))

    def run(self, request: RunRequest, runtime: RuntimeContext, callbacks: RunCallbacks | None = None) -> RunOutcome:
        action_def = self._bundle.action_map.get(request.action_id)
        if not action_def:
            raise KeyError(f"Unknown action: {request.action_id}")

        provider_cfg = dict(self._bundle.provider_cfg)
        if request.base_url_override:
            provider_cfg["ollama_base_url"] = request.base_url_override

        provider = build_provider(provider_cfg)
        action_service = ActionService(self._bus, provider)
        input_resolver = InputResolver(enable_selection_capture=runtime.use_selection)
        output_applier = OutputApplier()
        cancellation = CancellationController()

        output_mode = str(action_def.get("output_mode") or "stdout")
        if runtime.stream_to_stdout:
            self._bus.subscribe(
                EVENT_PIPELINE_UPDATE,
                lambda payload: print(payload.get("content", ""), end="", flush=True),
            )

        if request.explicit_messages is not None:
            resolved_input = InputResolution(text=request.explicit_text or "", source="explicit")
            messages = request.explicit_messages
            if callbacks and callbacks.on_input_resolved is not None:
                callbacks.on_input_resolved(resolved_input)
        else:
            input_mode = str(action_def.get("input_mode") or "selection_or_clipboard")
            resolved_input = input_resolver.resolve_text(request.explicit_text, input_mode=input_mode)
            if resolved_input.error:
                raise ValueError(resolved_input.error)
            if callbacks and callbacks.on_input_resolved is not None:
                callbacks.on_input_resolved(resolved_input)
            messages = self._build_messages(action_def, resolved_input.text)

        runtime_flags = {
            "provider": provider_cfg.get("provider", "ollama"),
            "model": request.model_override or action_def.get("model") or provider_cfg.get("default_model"),
            "stream": runtime.stream_enabled and self._default_stream_enabled(action_def),
            "temperature": action_def.get("temperature", self._bundle.app_cfg.get("temperature", 0.2)),
        }
        config = resolve_action_config(action_def, mode=runtime.mode, runtime_flags=runtime_flags)
        result = action_service.run_action(
            config,
            messages,
            cancellation_token=cancellation.token,
            source_meta=None,
            on_chunk=callbacks.on_chunk if callbacks else None,
        )
        if callbacks and callbacks.on_complete is not None:
            callbacks.on_complete(result)

        if runtime.apply_output and not (runtime.mode == "desktop_hotkey" and output_mode == "popup"):
            output_applier.apply(result.content, output_mode)

        return RunOutcome(
            action_id=config.action_id,
            action_name=config.action_name,
            input_resolution=resolved_input,
            output_mode=output_mode,
            result=result,
        )

    def _build_messages(self, action_def: dict[str, Any], user_input: str) -> list[dict[str, str]]:
        system_prompt = self._compose_system_prompt(action_def)
        prompt_template = str(action_def.get("prompt") or action_def.get("template") or "{input}")
        rendered = prompt_template.replace("{input}", user_input)

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": rendered})
        return messages

    def _compose_system_prompt(self, action_def: dict[str, Any]) -> str:
        global_prompt = str(self._bundle.app_cfg.get("system_prompt", "")).strip()
        action_prompt = str(action_def.get("system_prompt", "")).strip()
        parts = [part for part in (global_prompt, action_prompt) if part]
        return "\n\n".join(parts)
