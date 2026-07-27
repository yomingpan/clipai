from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from ClipAI.core.models import FeedbackOutcome, HotkeyEventType, LLMResult, ModelCatalogConnection, PressType, ProviderSettingsInput, RecipeComparisonResult, RecipeComparisonVerdict, RecipeManualTestCase, ResultRoute


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
class OpenRecipeImprovement:
    pass


@dataclass(frozen=True)
class BeginRecipeImprovement:
    action_id: str
    press_type: PressType


@dataclass(frozen=True)
class GenerateRecipeCandidate:
    selected_feedback_ids: tuple[str, ...]
    directions: tuple[str, ...]
    user_direction: str
    privacy_consent: bool
    operation_id: str


@dataclass(frozen=True)
class RecipeCandidateCompleted:
    operation_id: str
    result: LLMResult | None = None
    error: str = ""


@dataclass(frozen=True)
class RunRecipeCandidateTests:
    selected_feedback_ids: tuple[str, ...]
    manual_cases: tuple[RecipeManualTestCase, ...]
    operation_id: str
    saved_case_importance: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class RecipeTestProgress:
    operation_id: str
    current: int
    total: int


@dataclass(frozen=True)
class RecipeTestsCompleted:
    operation_id: str
    comparisons: tuple[RecipeComparisonResult, ...] = ()
    error: str = ""


@dataclass(frozen=True)
class SetRecipeComparisonVerdict:
    test_id: str
    verdict: RecipeComparisonVerdict
    candidate_parent_version: str = ""
    candidate_iteration: int = 0
    reasons: tuple[str, ...] = ()
    note: str = ""


@dataclass(frozen=True)
class ApplyRecipeCandidate:
    confirm_mixed_results: bool = False
    operation_id: str = ""
    candidate_parent_version: str = ""
    candidate_iteration: int = 0


@dataclass(frozen=True)
class CancelRecipeImprovementOperation:
    operation_id: str


@dataclass(frozen=True)
class OpenRecipeVersionHistory:
    action_id: str
    press_type: PressType


@dataclass(frozen=True)
class RestoreRecipeVersion:
    action_id: str
    press_type: PressType
    revision_id: str
    confirmed: bool = False
    operation_id: str = ""


@dataclass(frozen=True)
class KeepPersonalRecipeVersion:
    action_id: str
    press_type: PressType
    operation_id: str = ""


@dataclass(frozen=True)
class RefineRecipeCandidate:
    candidate_parent_version: str = ""
    candidate_iteration: int = 0


@dataclass(frozen=True)
class ReturnToRecipeCandidate:
    candidate_parent_version: str = ""
    candidate_iteration: int = 0


@dataclass(frozen=True)
class TreatRecipeIssueAsPrompt:
    action_version: str = ""


@dataclass(frozen=True)
class RetryFailedRecipeTests:
    operation_id: str


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


AppCommand: TypeAlias = ShortcutTriggered | StartAction | CloseSession | CancelSession | CopyResult | PasteResult | ArchiveResult | FollowUp | TogglePin | ShutdownApplication | ToggleSpeech | SpeakSelectionOrClipboard | ActivateWorkflow | ReleaseForegroundWorkflow | NavigateWorkflowBack | ExportDiagnostics | SelectProviderModel | SelectProvider | ReloadConfiguration | OpenProviderSettings | OpenRecipeImprovement | BeginRecipeImprovement | GenerateRecipeCandidate | RecipeCandidateCompleted | RunRecipeCandidateTests | RetryFailedRecipeTests | RecipeTestProgress | RecipeTestsCompleted | SetRecipeComparisonVerdict | ApplyRecipeCandidate | CancelRecipeImprovementOperation | OpenRecipeVersionHistory | RestoreRecipeVersion | KeepPersonalRecipeVersion | RefineRecipeCandidate | ReturnToRecipeCandidate | TreatRecipeIssueAsPrompt | ValidateAndSaveProviderSettings | RefreshProviderModels | SubmitActionFeedback | ActionFeedbackCompleted | SetFirstUseHintsEnabled | ResetFirstUseHints | GuidancePreferencesCompleted
