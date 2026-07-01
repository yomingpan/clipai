from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProviderRequest:
    messages: list[dict[str, str]]
    model: str
    temperature: float


class TextProvider(Protocol):
    def complete(self, request: ProviderRequest) -> str:
        """Return a plain text completion for a prepared request."""
