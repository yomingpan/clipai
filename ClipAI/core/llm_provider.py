from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Generator, Iterable

from clipai.core.cancellation import CancellationToken


class LLMError(Exception):
    pass


class LLMConnectionError(LLMError):
    pass


class LLMAuthError(LLMError):
    pass


class LLMRateLimitError(LLMError):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class LLMResponseError(LLMError):
    pass


class LLMCancelledError(LLMError):
    pass


@dataclass(frozen=True)
class ProviderChunk:
    content: str
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class ProviderResult:
    content: str
    usage: dict[str, Any] | None = None


class LLMProvider(ABC):
    def list_models(self) -> list[str]:
        return []

    @abstractmethod
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
        raise NotImplementedError


def map_http_error(status: int, message: str, retry_after: float | None = None) -> LLMError:
    if status in (401, 403):
        return LLMAuthError(message)
    if status == 429:
        return LLMRateLimitError(message, retry_after=retry_after)
    if status >= 500:
        return LLMConnectionError(message)
    return LLMResponseError(message)
