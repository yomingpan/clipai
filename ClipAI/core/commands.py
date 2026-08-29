from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias

from ClipAI.core.models import EntryActionRef, EntryPanelSelectionId, FeedbackOutcome, InputDocument, InterruptionScope, ModelCatalogConnection, ModifierHoldId, PasteOutcome, PasteTarget, PressType, ProviderSettingsInput, ResultRoute, ShortcutPressId, ShortcutPressOutcome, SpeechSpeed
from ClipAI.core.models import ControlSurfaceRef
from ClipAI.core.voice import VoiceCaptureId, VoiceDisableId, VoiceEngineEvent, VoiceLanguage, VoiceLanguageChangeId, VoiceSetupId


@dataclass(frozen=True)
class StartAction:
    action_id: str
    press_type: PressType
    result_route: ResultRoute = "popup"


@dataclass(frozen=True)
class OpenContextualQuestion:
    pass


@dataclass(frozen=True)
class SubmitContextualQuestion:
    workflow_id: str
    question: str = field(repr=False)


@dataclass(frozen=True)
class ContextualSourceCaptured:
    workflow_id: str
    capture_id: str
    document: InputDocument = field(repr=False)


@dataclass(frozen=True)
class ContextualSourceCaptureFailed:
    workflow_id: str
    capture_id: str
    message: str


@dataclass(frozen=True)
class WorkflowStepAccepted:
    workflow_id: str
    step_id: str


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
class OpenUnifiedEntryPanel:
    hold_id: ModifierHoldId


@dataclass(frozen=True)
class EntryPanelDigitPressed:
    hold_id: ModifierHoldId
    digit: str


@dataclass(frozen=True)
class EntryPanelInputPrepared:
    panel_id: str
    selection_id: EntryPanelSelectionId
    action: EntryActionRef
    document: InputDocument | None = field(default=None, repr=False)
    error: str = ""


@dataclass(frozen=True)
class CloseEntryPanel:
    panel_id: str


@dataclass(frozen=True)
class EntryPanelActionSelected:
    panel_id: str
    action: EntryActionRef


@dataclass(frozen=True)
class EntryPanelSlotSelected:
    panel_id: str
    slot: int


@dataclass(frozen=True)
class EntryPanelOpenMore:
    panel_id: str


@dataclass(frozen=True)
class EntryPanelSearchChanged:
    panel_id: str
    text: str


@dataclass(frozen=True)
class EntryPanelToggleDensity:
    panel_id: str


@dataclass(frozen=True)
class EntryPanelEscape:
    panel_id: str


@dataclass(frozen=True)
class InterruptionRequested:
    scope: InterruptionScope


ShortcutInputEvent: TypeAlias = (
    ShortcutKeyStateChanged
    | ShortcutPressStarted
    | ShortcutPressInvoked
    | ShortcutPressEnded
    | ShortcutAttemptRejected
    | OpenUnifiedEntryPanel
    | EntryPanelDigitPressed
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
class OpenPersonalStyles:
    pass


@dataclass(frozen=True)
class ClosePersonalStyles:
    pass


@dataclass(frozen=True)
class ImportPersonalStyle:
    path: str
    operation_id: str = ""


@dataclass(frozen=True)
class SelectPersonalStyle:
    profile_id: str
    operation_id: str = ""


@dataclass(frozen=True)
class PersonalStyleOperationCompleted:
    operation_id: str
    error: str = ""


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
class WorkflowAttentionCompleted:
    attention_id: str
    workflow_id: str
    focus_acquired: bool


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


@dataclass(frozen=True)
class SetSpeechSpeed:
    speed: SpeechSpeed
    operation_id: str = ""


@dataclass(frozen=True)
class SpeechSpeedPreferencesCompleted:
    operation_id: str
    error: str = ""


@dataclass(frozen=True)
class EnableVoiceInput:
    setup_id: VoiceSetupId


@dataclass(frozen=True)
class RetryVoiceInputSetup:
    """Explicitly discard ClipAI's saved WebView permission before retrying setup."""

    setup_id: VoiceSetupId


@dataclass(frozen=True)
class OpenVoiceSetup:
    pass


@dataclass(frozen=True)
class OpenVoicePermissionSettings:
    pass


@dataclass(frozen=True)
class VoicePreferenceSaved:
    setup_id: VoiceSetupId
    error: str = ""


@dataclass(frozen=True)
class DisableVoiceInput:
    disable_id: VoiceDisableId


@dataclass(frozen=True)
class VoiceDisableShutdownCompleted:
    disable_id: VoiceDisableId
    error: str = ""


@dataclass(frozen=True)
class VoiceDisablePreferenceSaved:
    disable_id: VoiceDisableId
    error: str = ""


@dataclass(frozen=True)
class VoiceEngineEventReceived:
    event: VoiceEngineEvent


@dataclass(frozen=True)
class StopVoiceCapture:
    capture_id: VoiceCaptureId


@dataclass(frozen=True)
class StartPopupVoiceCapture:
    workflow_id: str
    capture_id: VoiceCaptureId


@dataclass(frozen=True)
class CancelVoiceCapture:
    capture_id: VoiceCaptureId


@dataclass(frozen=True)
class VoiceCaptureWatchdogExpired:
    press_id: ShortcutPressId


@dataclass(frozen=True)
class VoiceSilenceWatchdogExpired:
    capture_id: VoiceCaptureId


@dataclass(frozen=True)
class SetVoiceLanguage:
    language: VoiceLanguage
    operation_id: VoiceLanguageChangeId = VoiceLanguageChangeId("")


@dataclass(frozen=True)
class VoiceLanguagePreferenceSaved:
    operation_id: VoiceLanguageChangeId
    error: str = ""


@dataclass(frozen=True)
class UpdateVoiceDraft:
    workflow_id: str
    expected_revision: int
    text: str


AppCommand: TypeAlias = ShortcutInputEvent | EntryPanelInputPrepared | CloseEntryPanel | EntryPanelActionSelected | EntryPanelSlotSelected | EntryPanelOpenMore | EntryPanelSearchChanged | EntryPanelToggleDensity | EntryPanelEscape | WorkflowStepAccepted | OpenShortcutGuide | CloseShortcutGuide | SelectShortcutGuideItem | StartAction | OpenContextualQuestion | SubmitContextualQuestion | ContextualSourceCaptured | ContextualSourceCaptureFailed | CloseSession | CancelSession | InterruptCurrent | InterruptAll | ControlSurfaceActivated | ControlSurfaceReleased | CloseProviderSettings | OpenPersonalStyles | ClosePersonalStyles | ImportPersonalStyle | SelectPersonalStyle | PersonalStyleOperationCompleted | CopyResult | PasteResult | PasteOperationCompleted | ExternalForegroundChanged | ArchiveResult | FollowUp | TogglePin | ShutdownApplication | ToggleSpeech | SpeakSelectionOrClipboard | ActivateWorkflow | NavigateWorkflowBack | WorkflowAttentionCompleted | ExportDiagnostics | SelectProviderModel | SelectProvider | ReloadConfiguration | OpenProviderSettings | ValidateAndSaveProviderSettings | RefreshProviderModels | SubmitActionFeedback | ActionFeedbackCompleted | SetFirstUseHintsEnabled | ResetFirstUseHints | GuidancePreferencesCompleted | SetSpeechSpeed | SpeechSpeedPreferencesCompleted | OpenVoiceSetup | OpenVoicePermissionSettings | EnableVoiceInput | RetryVoiceInputSetup | VoicePreferenceSaved | DisableVoiceInput | VoiceDisableShutdownCompleted | VoiceDisablePreferenceSaved | VoiceEngineEventReceived | StartPopupVoiceCapture | StopVoiceCapture | CancelVoiceCapture | VoiceCaptureWatchdogExpired | VoiceSilenceWatchdogExpired | SetVoiceLanguage | VoiceLanguagePreferenceSaved | UpdateVoiceDraft
