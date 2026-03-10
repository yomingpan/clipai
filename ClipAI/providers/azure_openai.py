from __future__ import annotations

from typing import Any, Generator, Iterable

from clipai.core.cancellation import CancellationToken
from clipai.core.llm_provider import LLMProvider, ProviderChunk, ProviderResult


class AzureOpenAIProvider(LLMProvider):
    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config

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
        del model, stream, temperature, image_base64, cancellation_token, kwargs
        text = "AzureOpenAI provider placeholder"
        yield ProviderChunk(content=text)
        return ProviderResult(content=text)
