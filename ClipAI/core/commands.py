from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias

from ClipAI.core.models import HotkeyEventType, PressType, ResultRoute


@dataclass(frozen=True)
class StartAction:
    action_id: str
    press_type: PressType
    result_route: ResultRoute = "popup"


@dataclass(frozen=True)
class ShortcutTriggered:
    shortcut_id: str
    press_type: HotkeyEventType


@dataclass(frozen=True)
class CloseSession:
    session_id: str


@dataclass(frozen=True)
class CancelSession:
    session_id: str


@dataclass(frozen=True)
class CopyResult:
    session_id: str
    text: str | None = None
    operation_id: str = ""


@dataclass(frozen=True)
class FollowUp:
    session_id: str
    text: str


@dataclass(frozen=True)
class TogglePin:
    session_id: str


@dataclass(frozen=True)
class ShutdownApplication:
    pass


@dataclass(frozen=True)
class ToggleSpeech:
    session_id: str
    text: str | None = None
    operation_id: str = ""


@dataclass(frozen=True)
class SpeakSelectionOrClipboard:
    pass


@dataclass(frozen=True)
class ActivateWorkflow:
    workflow_id: str


@dataclass(frozen=True)
class NavigateWorkflowBack:
    workflow_id: str


@dataclass(frozen=True)
class PasteResult:
    session_id: str
    text: str | None = None
    operation_id: str = ""


@dataclass(frozen=True)
class ArchiveResult:
    session_id: str
    text: str | None = None
    operation_id: str = ""


@dataclass(frozen=True)
class ExportDiagnostics:
    pass


@dataclass(frozen=True)
class SelectProviderModel:
    provider: str
    model: str


@dataclass(frozen=True)
class SelectProvider:
    provider: str


@dataclass(frozen=True)
class ReloadConfiguration:
    pass


@dataclass(frozen=True)
class OpenProviderSettings:
    provider: str | None = None


@dataclass(frozen=True)
class ValidateAndSaveProviderSettings:
    provider: str
    model: str
    api_key: str = field(repr=False)
    operation_id: str = ""
    server_name: str = ""
    base_url: str = field(default="", repr=False)


AppCommand: TypeAlias = ShortcutTriggered | StartAction | CloseSession | CancelSession | CopyResult | PasteResult | ArchiveResult | FollowUp | TogglePin | ShutdownApplication | ToggleSpeech | SpeakSelectionOrClipboard | ActivateWorkflow | NavigateWorkflowBack | ExportDiagnostics | SelectProviderModel | SelectProvider | ReloadConfiguration | OpenProviderSettings | ValidateAndSaveProviderSettings
