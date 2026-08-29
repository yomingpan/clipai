from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ClipAI.core.models import ReadinessIssue
from ClipAI.providers.settings import AnthropicSettings, GatewaySettings, GeminiSettings, OpenAISettings, ProviderSettings
from ClipAI.services.action_catalog import ActionCatalog
from ClipAI.services.entry_panel import EntryPanelCatalog
from ClipAI.services.shortcut_catalog import ShortcutCatalog
from ClipAI.services.output_profiles import OutputProfileCatalog
from ClipAI.support.logging_setup import LoggingSettings

ProviderName = Literal["fake", "gemini", "openai", "anthropic", "gateway"]
ModifierMode = Literal["alt_shift", "ctrl_shift", "ctrl_alt"]


@dataclass(frozen=True)
class AppSettings:
    temperature: float
    stream: bool
    modifier_mode: ModifierMode
    system_prompt: str
    entry_panel_enabled: bool = False


@dataclass(frozen=True)
class RuntimeSettings:
    maintenance_workers: int = 1


@dataclass(frozen=True)
class TTSSettings:
    enabled: bool
    voice: str
    rate: str
    volume: str
    english_voice: str = "en-US-AndrewNeural"
    japanese_voice: str = "ja-JP-NanamiNeural"


@dataclass(frozen=True)
class VoiceInputSettings:
    """V1 has one deliberate engine path: controlled Edge WebView2 Browser Speech."""

    backend: Literal["edge_webview2_browser_speech"]


@dataclass(frozen=True)
class ProviderCatalog:
    active: ProviderName
    gemini: GeminiSettings
    openai: OpenAISettings
    anthropic: AnthropicSettings
    gateway: GatewaySettings

    def active_settings(self) -> ProviderSettings | None:
        if self.active == "fake":
            return None
        return getattr(self, self.active)


@dataclass(frozen=True)
class ConfigSchemaVersions:
    app: int
    actions: int
    output_profiles: int
    shortcuts: int
    entry_panel: int


@dataclass(frozen=True)
class ConfigBundle:
    app: AppSettings
    runtime: RuntimeSettings
    providers: ProviderCatalog
    actions: ActionCatalog
    shortcuts: ShortcutCatalog
    tts: TTSSettings
    voice_input: VoiceInputSettings
    logging: LoggingSettings
    output_profiles: OutputProfileCatalog
    entry_panel: EntryPanelCatalog
    schema_versions: ConfigSchemaVersions
    readiness_issues: tuple[ReadinessIssue, ...] = ()
