from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderCredential:
    """A resolved provider secret. Its value must never appear in repr or logs."""

    env_name: str
    value: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class GeminiSettings:
    api_key_env: str
    base_url: str
    model: str
    timeout_sec: float


@dataclass(frozen=True)
class OpenAISettings:
    api_key_env: str
    base_url: str
    model: str
    timeout_sec: float


@dataclass(frozen=True)
class AnthropicSettings:
    api_key_env: str
    base_url: str
    model: str
    timeout_sec: float
    api_version: str
    max_tokens: int


ProviderSettings = GeminiSettings | OpenAISettings | AnthropicSettings
