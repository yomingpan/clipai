from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ProviderError(RuntimeError):
    """Base provider error surfaced to the workflow."""


class ProviderConfigurationError(ProviderError):
    """Provider cannot run because required configuration is missing."""


class ProviderResponseError(ProviderError):
    """Provider returned an error or unusable response."""


@dataclass(frozen=True)
class ProviderRequest:
    messages: list[dict[str, str]]
    model: str
    temperature: float


class TextProvider(Protocol):
    def complete(self, request: ProviderRequest) -> str:
        """Return a plain text completion for a prepared request."""
