from __future__ import annotations

from dataclasses import dataclass


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
