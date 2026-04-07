from __future__ import annotations

from typing import Any, Generator, Iterable

from clipai.core.cancellation import CancellationToken
from clipai.core.llm_provider import LLMProvider, ProviderChunk, ProviderResult


class OpenAICompactProvider(LLMProvider):
    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config

    def list_models(self) -> list[str]:
        model = str(self._config.get("default_model") or "").strip()
        return [model] if model else []

    def chat_completion(
        self,
        messages: Iterable[dict[str, Any]],
        model: str,
        stream: bool,
        temperature: float,
        image_base64: str | None,
        cancellation_token: CancellationToken | None,
        **kwargs: Any,
    ) -> Generator[ProviderChunk, None, ProviderResult]:
        del messages, model, stream, temperature, image_base64, cancellation_token, kwargs
        text = "OpenAI compact provider placeholder"
        yield ProviderChunk(content=text)
        return ProviderResult(content=text)
