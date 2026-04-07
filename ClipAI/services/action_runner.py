from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Any, Callable

from clipai.app.config import AppConfigBundle
from clipai.actions import ResolvedAction, resolve_action_variant
from clipai.context.input_resolver import InputResolution, InputResolver
from clipai.context.runtime_context import RuntimeContext
from clipai.core.cancellation import CancellationController
from clipai.core.constants import EVENT_PIPELINE_UPDATE
from clipai.core.event_bus import EventBus
from clipai.providers.factory import build_provider
from clipai.services.action_config import resolve_action_config
from clipai.services.hedged_action_service import HedgeRoute, HedgedActionService
from clipai.services.action_service import ActionRunResult, ActionService
from clipai.services.output_applier import OutputApplier

logger = logging.getLogger("clipai.action_runner")


@dataclass(frozen=True)
class RunRequest:
    action_id: str
    press_type: str = "short"
    explicit_text: str | None = None
    explicit_messages: list[dict[str, str]] | None = None
    output_mode_override: str | None = None
    model_override: str | None = None
    base_url_override: str | None = None


@dataclass(frozen=True)
class RunOutcome:
    action_id: str
    action_name: str
    press_type: str
    input_resolution: InputResolution
    output_mode: str
    provider_name: str
    model_name: str
    result: ActionRunResult


@dataclass(frozen=True)
class RunCallbacks:
    on_input_resolved: Callable[[InputResolution], None] | None = None
    on_chunk: Callable[[str], None] | None = None
    on_complete: Callable[[ActionRunResult], None] | None = None


@dataclass(frozen=True)
class _ExecutionOutcome:
    result: ActionRunResult
    provider_name: str
    model_name: str


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

    @staticmethod
    def _provider_supports_image(provider_name: str) -> bool:
        return provider_name.lower() in {"gemini", "ollama", "olama"}

    def run(self, request: RunRequest, runtime: RuntimeContext, callbacks: RunCallbacks | None = None) -> RunOutcome:
        action_def = self._bundle.action_map.get(request.action_id)
        if not action_def:
            raise KeyError(f"Unknown action: {request.action_id}")
        resolved_action = resolve_action_variant(action_def, request.press_type)
        return self.run_resolved_action(
            resolved_action,
            runtime,
            callbacks=callbacks,
            explicit_text=request.explicit_text,
            explicit_messages=request.explicit_messages,
            output_mode_override=request.output_mode_override,
            model_override=request.model_override,
            base_url_override=request.base_url_override,
        )

    def run_resolved_action(
        self,
        resolved_action: ResolvedAction,
        runtime: RuntimeContext,
        callbacks: RunCallbacks | None = None,
        *,
        explicit_text: str | None = None,
        explicit_messages: list[dict[str, str]] | None = None,
        output_mode_override: str | None = None,
        model_override: str | None = None,
        base_url_override: str | None = None,
    ) -> RunOutcome:
        action_def = dict(resolved_action.action_def)

        provider_cfg = dict(self._bundle.provider_cfg)
        if action_def.get("provider"):
            provider_cfg["provider"] = action_def["provider"]
        if base_url_override:
            provider_cfg["ollama_base_url"] = base_url_override

        provider = build_provider(provider_cfg)
        action_service = ActionService(self._bus, provider)
        input_resolver = InputResolver(enable_selection_capture=runtime.use_selection)
        output_applier = OutputApplier()
        cancellation = CancellationController()

        output_mode = str(output_mode_override or action_def.get("output_mode") or "stdout")
        logger.info(
            "[clipai] Run start: action_id=%s press_type=%s action_name=%s output_mode=%s mode=%s use_selection=%s apply_output=%s variant_applied=%s popup_chain_session_id=%s",
            resolved_action.action_id,
            resolved_action.press_type,
            resolved_action.action_name,
            output_mode,
            runtime.mode,
            runtime.use_selection,
            runtime.apply_output,
            resolved_action.variant_applied,
            runtime.popup_chain_session_id or "",
        )
        if runtime.stream_to_stdout:
            self._bus.subscribe(
                EVENT_PIPELINE_UPDATE,
                lambda payload: print(payload.get("content", ""), end="", flush=True),
            )

        if explicit_messages is not None:
            resolved_input = InputResolution(text=explicit_text or "", source="explicit")
            messages = explicit_messages
            if callbacks and callbacks.on_input_resolved is not None:
                callbacks.on_input_resolved(resolved_input)
        else:
            input_mode = str(action_def.get("input_mode") or "selection_or_clipboard")
            resolved_input = input_resolver.resolve_text(explicit_text, input_mode=input_mode)
            if resolved_input.error:
                logger.error(
                    "[clipai] Input resolution failed: action_id=%s input_mode=%s source=%s error=%s",
                    resolved_action.action_id,
                    input_mode,
                    resolved_input.source,
                    resolved_input.error,
                )
                raise ValueError(resolved_input.error)
            logger.info(
                "[clipai] Input resolved: action_id=%s input_mode=%s source=%s chars=%s has_image=%s",
                resolved_action.action_id,
                input_mode,
                resolved_input.source,
                len(resolved_input.text or ""),
                bool(resolved_input.image_base64),
            )
            if callbacks and callbacks.on_input_resolved is not None:
                callbacks.on_input_resolved(resolved_input)
            messages = self._build_messages(action_def, resolved_input.text)

        source_meta = self._source_meta_for_input(resolved_input)
        provider_name = str(provider_cfg.get("provider") or "")
        if source_meta.get("image_base64") and not self._provider_supports_image(provider_name):
            raise ValueError(f"Provider '{provider_name}' does not support clipboard image input.")

        runtime_flags = {
            "provider": provider_cfg.get("provider", "ollama"),
            "model": model_override or action_def.get("model") or provider_cfg.get("default_model"),
            "stream": runtime.stream_enabled and self._default_stream_enabled(action_def),
            "temperature": action_def.get("temperature", self._bundle.app_cfg.get("temperature", 0.2)),
        }
        config = resolve_action_config(action_def, mode=runtime.mode, runtime_flags=runtime_flags)
        execution = self._run_action_request(
            action_def=action_def,
            config=config,
            provider_cfg=provider_cfg,
            action_service=action_service,
            messages=messages,
            cancellation=cancellation,
            source_meta=source_meta,
            output_mode=output_mode,
            runtime=runtime,
            on_chunk=callbacks.on_chunk if callbacks else None,
        )
        result = execution.result
        logger.info(
            "[clipai] Run complete: action_id=%s press_type=%s model=%s chars=%s",
            config.action_id,
            resolved_action.press_type,
            execution.model_name,
            len(result.content or ""),
        )
        if callbacks and callbacks.on_complete is not None:
            callbacks.on_complete(result)

        if runtime.apply_output and not (runtime.mode == "desktop_hotkey" and output_mode == "popup"):
            logger.info("[clipai] Applying output: action_id=%s output_mode=%s", config.action_id, output_mode)
            output_applier.apply(result.content, output_mode)

        return RunOutcome(
            action_id=config.action_id,
            action_name=config.action_name,
            press_type=resolved_action.press_type,
            input_resolution=resolved_input,
            output_mode=output_mode,
            provider_name=execution.provider_name,
            model_name=execution.model_name,
            result=result,
        )

    @staticmethod
    def _source_meta_for_input(resolved_input: InputResolution) -> dict[str, Any]:
        source_meta: dict[str, Any] = {}
        if resolved_input.image_base64:
            source_meta["image_base64"] = resolved_input.image_base64
        return source_meta

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

    def _run_action_request(
        self,
        *,
        action_def: dict[str, Any],
        config,
        provider_cfg: dict[str, Any],
        action_service: ActionService,
        messages: list[dict[str, str]],
        cancellation: CancellationController,
        source_meta: dict[str, Any],
        output_mode: str,
        runtime: RuntimeContext,
        on_chunk: Callable[[str], None] | None,
    ) -> _ExecutionOutcome:
        if not self._should_use_hedge(action_def, output_mode, runtime):
            return self._run_with_default_model_fallback(
                config=config,
                provider_cfg=provider_cfg,
                action_service=action_service,
                messages=messages,
                cancellation=cancellation,
                source_meta=source_meta,
                on_chunk=on_chunk,
            )

        secondary_provider_name = str(
            action_def.get("hedge_secondary_provider")
            or self._bundle.app_cfg.get("hedge_secondary_provider")
            or provider_cfg.get("provider")
            or ""
        ).strip()
        secondary_model = str(
            action_def.get("hedge_secondary_model")
            or self._bundle.app_cfg.get("hedge_secondary_model")
            or provider_cfg.get("default_model")
            or config.model
        ).strip()
        hedge_delay_ms = int(
            action_def.get("hedge_delay_ms")
            or self._bundle.app_cfg.get("hedge_delay_ms")
            or 150
        )
        fallback_cfg = dict(provider_cfg)
        if secondary_provider_name:
            fallback_cfg["provider"] = secondary_provider_name
        if secondary_model:
            fallback_cfg["default_model"] = secondary_model

        hedged_service = HedgedActionService(self._bus)
        result = hedged_service.run_action(
            config,
            messages,
            HedgeRoute(
                name="primary",
                provider=build_provider(provider_cfg),
                model=config.model,
                provider_name=str(provider_cfg.get("provider", config.provider)),
            ),
            HedgeRoute(
                name="fallback",
                provider=build_provider(fallback_cfg),
                model=secondary_model or config.model,
                provider_name=str(fallback_cfg.get("provider", config.provider)),
            ),
            temperature=config.temperature,
            stream=config.stream,
            source_meta=source_meta,
            on_chunk=on_chunk,
            hedge_delay_ms=hedge_delay_ms,
        )
        return _ExecutionOutcome(
            result=result,
            provider_name=result.provider_name or str(provider_cfg.get("provider", config.provider)),
            model_name=result.model_name or config.model,
        )

    def _run_with_default_model_fallback(
        self,
        *,
        config,
        provider_cfg: dict[str, Any],
        action_service: ActionService,
        messages: list[dict[str, str]],
        cancellation: CancellationController,
        source_meta: dict[str, Any],
        on_chunk: Callable[[str], None] | None,
    ) -> _ExecutionOutcome:
        try:
            result = action_service.run_action(
                config,
                messages,
                cancellation_token=cancellation.token,
                source_meta=source_meta,
                on_chunk=on_chunk,
            )
            return _ExecutionOutcome(
                result=result,
                provider_name=result.provider_name or config.provider,
                model_name=result.model_name or config.model,
            )
        except Exception:
            default_model = str(provider_cfg.get("default_model") or "").strip()
            if not default_model or default_model == config.model:
                raise
            logger.warning(
                "[clipai] Model failed, retrying with default model: provider=%s model=%s fallback_model=%s",
                config.provider,
                config.model,
                default_model,
            )
            fallback_config = replace(config, model=default_model)
            result = action_service.run_action(
                fallback_config,
                messages,
                cancellation_token=cancellation.token,
                source_meta=source_meta,
                on_chunk=on_chunk,
            )
            return _ExecutionOutcome(
                result=result,
                provider_name=result.provider_name or fallback_config.provider,
                model_name=result.model_name or fallback_config.model,
            )

    def _should_use_hedge(self, action_def: dict[str, Any], output_mode: str, runtime: RuntimeContext) -> bool:
        if runtime.mode != "desktop_hotkey":
            return False
        if output_mode != "popup":
            return False
        return bool(action_def.get("hedge_enabled", self._bundle.app_cfg.get("hedge_enabled", False)))
