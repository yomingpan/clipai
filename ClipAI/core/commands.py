from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from ClipAI.core.models import FeedbackOutcome, InterruptionScope, ModelCatalogConnection, PasteOutcome, PasteTarget, PressType, ProviderSettingsInput, ResultRoute, ShortcutPressId, ShortcutPressOutcome
from ClipAI.core.models import ControlSurfaceRef


@dataclass(frozen=True)
class StartAction:
    action_id: str
    press_type: PressType
    result_route: ResultRoute = "popup"


@dataclass(frozen=True)
class ShortcutKeyStateChanged:
    pressed_keys: frozenset[str]


@dataclass(frozen=True)
class ShortcutPressStarted:
    press_id: ShortcutPressId
    shortcut_id: str


@dataclass(frozen=True)
class ShortcutPressInvoked:
    press_id: ShortcutPressId
    shortcut_id: str
    press_type: PressType


@dataclass(frozen=True)
class ShortcutPressEnded:
    press_id: ShortcutPressId
    shortcut_id: str
    outcome: ShortcutPressOutcome


@dataclass(frozen=True)
class ShortcutAttemptRejected:
    pass


@dataclass(frozen=True)
class InterruptionRequested:
    scope: InterruptionScope


ShortcutInputEvent: TypeAlias = (
    ShortcutKeyStateChanged
    | ShortcutPressStarted
    | ShortcutPressInvoked
    | ShortcutPressEnded
    | ShortcutAttemptRejected
    | InterruptionRequested
)


@dataclass(frozen=True)
class OpenShortcutGuide:
    guide_id: str


@dataclass(frozen=True)
class CloseShortcutGuide:
    guide_id: str


@dataclass(frozen=True)
class SelectShortcutGuideItem:
    shortcut_id: str


@dataclass(frozen=True)
class CloseSession:
    session_id: str


@dataclass(frozen=True)
class CancelSession:
    session_id: str


@dataclass(frozen=True)
class InterruptCurrent:
    pass


@dataclass(frozen=True)
class InterruptAll:
    pass


@dataclass(frozen=True)
class ControlSurfaceActivated:
    surface: ControlSurfaceRef


@dataclass(frozen=True)
class ControlSurfaceReleased:
    surface: ControlSurfaceRef


@dataclass(frozen=True)
class CloseProviderSettings:
    pass


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
class ReleaseForegroundWorkflow:
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
class PasteOperationCompleted:
    operation_id: str
    workflow_id: str
    outcome: PasteOutcome


@dataclass(frozen=True)
class ExternalForegroundChanged:
    target: PasteTarget


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
    settings: ProviderSettingsInput
    operation_id: str = ""


@dataclass(frozen=True)
class RefreshProviderModels:
    provider: str = ""
    operation_id: str = ""
    connection: ModelCatalogConnection | None = None


@dataclass(frozen=True)
class SubmitActionFeedback:
    session_id: str
    step_id: str
    operation_id: str
    outcome: FeedbackOutcome
    reason: str = ""
    note: str = ""
    save_case: bool = False


@dataclass(frozen=True)
class ActionFeedbackCompleted:
    session_id: str
    step_id: str
    operation_id: str
    error: str = ""


@dataclass(frozen=True)
class SetFirstUseHintsEnabled:
    enabled: bool
    operation_id: str = ""


@dataclass(frozen=True)
class ResetFirstUseHints:
    operation_id: str = ""


@dataclass(frozen=True)
class GuidancePreferencesCompleted:
    operation_id: str
    error: str = ""


AppCommand: TypeAlias = ShortcutInputEvent | OpenShortcutGuide | CloseShortcutGuide | SelectShortcutGuideItem | StartAction | CloseSession | CancelSession | InterruptCurrent | InterruptAll | ControlSurfaceActivated | ControlSurfaceReleased | CloseProviderSettings | CopyResult | PasteResult | PasteOperationCompleted | ExternalForegroundChanged | ArchiveResult | FollowUp | TogglePin | ShutdownApplication | ToggleSpeech | SpeakSelectionOrClipboard | ActivateWorkflow | ReleaseForegroundWorkflow | NavigateWorkflowBack | ExportDiagnostics | SelectProviderModel | SelectProvider | ReloadConfiguration | OpenProviderSettings | ValidateAndSaveProviderSettings | RefreshProviderModels | SubmitActionFeedback | ActionFeedbackCompleted | SetFirstUseHintsEnabled | ResetFirstUseHints | GuidancePreferencesCompleted
