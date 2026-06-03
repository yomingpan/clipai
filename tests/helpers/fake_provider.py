from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generator, Iterable

from clipai.core.cancellation import CancellationToken
from clipai.core.llm_provider import LLMProvider, ProviderChunk, ProviderResult


@dataclass
class ProviderCall:
    messages: list[dict[str, Any]]
    model: str
    stream: bool
    temperature: float
    image_base64: str | None


@dataclass
class FakeProvider(LLMProvider):
    content: str = "fake response"
    chunks: list[str] | None = None
    models: list[str] = field(default_factory=lambda: ["fake-model"])
    calls: list[ProviderCall] = field(default_factory=list)

    def list_models(self) -> list[str]:
        return list(self.models)

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
        del kwargs
        if cancellation_token is not None:
            cancellation_token.throw_if_cancelled()
        message_list = [dict(message) for message in messages]
        self.calls.append(
            ProviderCall(
                messages=message_list,
                model=model,
                stream=stream,
                temperature=temperature,
                image_base64=image_base64,
            )
        )
        emitted = self.chunks if self.chunks is not None else [self.content]
        for chunk in emitted:
            if cancellation_token is not None:
                cancellation_token.throw_if_cancelled()
            yield ProviderChunk(chunk)
        return ProviderResult(content="".join(emitted), usage={"fake": True})
