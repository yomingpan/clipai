from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ClipAI.providers.settings import AnthropicSettings, GeminiSettings, OpenAISettings, ProviderSettings
from ClipAI.services.action_catalog import ActionCatalog
from ClipAI.support.logging_setup import LoggingSettings

ProviderName = Literal["fake", "gemini", "openai", "anthropic"]
ModifierMode = Literal["alt_shift", "ctrl_shift", "ctrl_alt"]


@dataclass(frozen=True)
class AppSettings:
    temperature: float
    stream: bool
    modifier_mode: ModifierMode
    system_prompt: str


@dataclass(frozen=True)
class RuntimeSettings:
    max_workers: int = 2


@dataclass(frozen=True)
class TTSSettings:
    enabled: bool
    voice: str
    rate: str
    volume: str


@dataclass(frozen=True)
class VoiceOpenAISettings:
    api_key_env: str
    base_url: str
    model: str
    language: str
    timeout_sec: float


@dataclass(frozen=True)
class VoiceInputSettings:
    backend: str
    browser: str
    host: str
    port: int
    allow_port_fallback: bool
    language: str
    auto_start: bool
    clipboard_mode: str
    openai: VoiceOpenAISettings


@dataclass(frozen=True)
class ProviderCatalog:
    active: ProviderName
    gemini: GeminiSettings
    openai: OpenAISettings
    anthropic: AnthropicSettings

    def active_settings(self) -> ProviderSettings | None:
        if self.active == "fake":
            return None
        return getattr(self, self.active)


@dataclass(frozen=True)
class ConfigBundle:
    app: AppSettings
    runtime: RuntimeSettings
    providers: ProviderCatalog
    actions: ActionCatalog
    tts: TTSSettings
    voice_input: VoiceInputSettings
    logging: LoggingSettings
