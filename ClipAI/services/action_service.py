from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from clipai.core.constants import (
    EVENT_ACTION_COMPLETE,
    EVENT_ACTION_ERROR,
    EVENT_ACTION_START,
    EVENT_PIPELINE_UPDATE,
)
from clipai.core.event_bus import EventBus
from clipai.core.llm_provider import LLMError
from clipai.services.action_config import ResolvedActionConfig


@dataclass(frozen=True)
class ActionRunResult:
    action_id: str
    content: str
    provider_name: str = ""
    model_name: str = ""


class ActionService:
    def __init__(self, event_bus: EventBus, provider: Any) -> None:
        self._event_bus = event_bus
        self._provider = provider

    def run_action(
        self,
        config: ResolvedActionConfig,
        messages: list[dict[str, Any]],
        cancellation_token,
        source_meta: dict[str, Any] | None = None,
        on_chunk: Callable[[str], None] | None = None,
    ) -> ActionRunResult:
        if source_meta is not None and not isinstance(source_meta, dict):
            if cancellation_token is None:
                cancellation_token = source_meta
            source_meta = None
        source_meta = source_meta or {}
        started = time.time()
        now_ms = int(started * 1000)
        self._event_bus.publish(
            EVENT_ACTION_START,
            {
                "action_id": config.action_id,
                "action_name": config.action_name,
                "mode": config.mode,
                "ts": now_ms,
            },
        )

        content_parts: list[str] = []
        try:
            iterator = self._provider.chat_completion(
                messages=messages,
                model=config.model,
                stream=config.stream,
                temperature=config.temperature,
                image_base64=source_meta.get("image_base64"),
                cancellation_token=cancellation_token,
            )
            for chunk in iterator:
                if cancellation_token:
                    cancellation_token.throw_if_cancelled()
                content_parts.append(chunk.content)
                self._event_bus.publish(
                    EVENT_PIPELINE_UPDATE,
                    {
                        "content": chunk.content,
                        "source_meta": source_meta,
                        "action_id": config.action_id,
                        "ts": int(time.time() * 1000),
                    },
                )
                if on_chunk is not None:
                    on_chunk(chunk.content)
        except Exception as exc:
            error_type = exc.__class__.__name__
            if isinstance(exc, LLMError):
                message = str(exc)
            else:
                message = f"unexpected error: {exc}"
            self._event_bus.publish(
                EVENT_ACTION_ERROR,
                {
                    "action_id": config.action_id,
                    "error_type": error_type,
                    "message": message,
                    "ts": int(time.time() * 1000),
                },
            )
            raise

        duration_ms = int((time.time() - started) * 1000)
        final_content = "".join(content_parts)
        self._event_bus.publish(
            EVENT_ACTION_COMPLETE,
            {
                "action_id": config.action_id,
                "summary": final_content[:120],
                "duration_ms": duration_ms,
                "ts": int(time.time() * 1000),
            },
        )
        return ActionRunResult(
            action_id=config.action_id,
            content=final_content,
            provider_name=config.provider,
            model_name=config.model,
        )
