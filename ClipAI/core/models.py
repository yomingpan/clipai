from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, NewType

from ClipAI.core.errors import PasteFailureReason
from ClipAI.core.state import CancellationToken

PressType = Literal["short", "long"]
ShortcutPressId = NewType("ShortcutPressId", int)
ShortcutPressOutcome = Literal["released", "cancelled"]
InterruptionScope = Literal["current", "all"]
ShortcutGuidePhase = Literal["listening", "keys_pressed", "recognized", "invalid"]
MessageRole = Literal["system", "user", "assistant"]
ImageSource = Literal["clipboard"]
InputMode = Literal["clipboard", "clipboard_image", "selection_or_clipboard"]
OutputMode = Literal["popup"]
ExternalFallback = Literal["selection_or_clipboard", "clipboard"]
PersonalStyleMode = Literal["formal", "informal"]
ResultRoute = Literal["popup", "speech"]
SpeechSpeed = Literal["slow", "normal", "fast", "super_fast"]
VoiceLanguagePreference = Literal["zh-TW", "en-US"]
ApplicationStatus = Literal["idle", "processing", "success", "warning", "error", "paused"]
OperationKind = Literal["llm", "tts", "copy", "paste", "archive"]
FeedbackOutcome = Literal["helpful", "needs_adjustment", "not_applicable"]
FeedbackOperationState = Literal["idle", "pending", "succeeded", "failed"]
PresentationBlockKind = Literal["paragraph", "heading", "unordered_item", "ordered_item", "spacer"]
InlineStyle = Literal["plain", "bold", "italic"]
ShortcutCommandKind = Literal[
    "start_action",
    "open_contextual_question",
    "speak_selection_or_clipboard",
    "push_to_talk",
]
OutputActionKind = Literal["copy", "paste", "archive", "speech"]
OutputOperationState = Literal[
    "pending",
    "succeeded",
    "failed",
    "cancelled",
    "dispatched_unconfirmed",
    "cleanup_failed",
]
PasteDeliveryState = Literal["not_dispatched", "dispatched_unconfirmed"]
PasteCleanupState = Literal["not_required", "restored", "external_change", "failed"]
PasteCompletionState = Literal["failed", "cancelled", "dispatched_unconfirmed", "cleanup_failed"]
ResultCompleteness = Literal["none", "partial", "complete"]
ActionStartAdmissionState = Literal["accepted", "rejected", "blocked"]
SettingsOperationState = Literal["idle", "pending", "succeeded", "failed"]
ProviderSettingsOperationKind = Literal["save", "refresh"]
ControlSurfaceKind = Literal["workflow", "provider_settings", "shortcut_guide", "personal_styles"]
InterruptibleOperationKind = Literal[
    "workflow",
    "speech",
    "copy",
    "paste",
    "archive",
    "shortcut_sequence",
    "provider_configuration",
]


@dataclass(frozen=True)
class ShortcutPressRef:
    press_id: ShortcutPressId
    shortcut_id: str


@dataclass(frozen=True)
class EntryActionRef:
    action_id: str
    press_type: PressType


@dataclass(frozen=True)
class ActionStartAdmission:
    state: ActionStartAdmissionState
    reason: str = ""
    message: str = ""

    @property
    def accepted(self) -> bool:
        return self.state == "accepted"


@dataclass(frozen=True)
class ShortcutObservationSnapshot:
    pressed_keys: frozenset[str] = frozenset()
    active_presses: tuple[ShortcutPressRef, ...] = ()


@dataclass(frozen=True)
class ControlSurfaceRef:
    surface_id: str
    kind: ControlSurfaceKind


@dataclass(frozen=True)
class InterruptibleOperationRef:
    operation_id: str
    kind: InterruptibleOperationKind
    workflow_id: str = ""
    surface_id: str = ""


@dataclass(frozen=True)
class InterruptionPlan:
    surface: ControlSurfaceRef | None = None
    operations: tuple[InterruptibleOperationRef, ...] = ()


@dataclass(frozen=True)
class ModelSelectionState:
    provider: str
    available_models: tuple[str, ...]
    selected_model: str
    pending_model: str | None = None
    refreshing: bool = False
    custom_models: tuple[str, ...] = ()
    configuration_pending: bool = False


@dataclass(frozen=True)
class ProviderCapabilities:
    custom_endpoint: bool = False
    credential_optional: bool = False
    editable_model: bool = False
    validation_may_incur_cost: bool = False


@dataclass(frozen=True)
class ProviderOption:
    provider_id: str
    display_name: str
    available_models: tuple[str, ...]
    selected_model: str
    configured: bool
    custom_models: tuple[str, ...] = ()
    credential_hint: str = ""
    capabilities: ProviderCapabilities = ProviderCapabilities()


@dataclass(frozen=True)
class ProviderSelectionState:
    providers: tuple[ProviderOption, ...]
    selected_provider: str
    pending_provider: str | None = None
    reloading: bool = False
    configuration_pending: bool = False


@dataclass(frozen=True)
class SpeechSpeedState:
    selected_speed: SpeechSpeed | None
    pending_speed: SpeechSpeed | None = None
    update_pending: bool = False
    available: bool = True


@dataclass(frozen=True)
class VoicePreferencesState:
    enabled: bool = False
    language: VoiceLanguagePreference = "zh-TW"
    update_pending: bool = False


@dataclass(frozen=True)
class EnvironmentSetting:
    name: str
    value: str


@dataclass(frozen=True)
class ProviderSettingsState:
    providers: tuple[ProviderOption, ...]
    selected_provider: str
    selected_model: str
    operation_state: SettingsOperationState = "idle"
    operation_kind: ProviderSettingsOperationKind | None = None
    message: str = ""
    operation_id: str = ""
    connection_name: str = ""
    connection_base_url: str = ""


@dataclass(frozen=True)
class ProviderSettingsInput:
    provider: str
    model: str
    api_key: str = field(default="", repr=False)
    connection_name: str = ""
    connection_base_url: str = field(default="", repr=False)


@dataclass(frozen=True)
class PersonalStyleProfile:
    profile_id: str
    name: str
    guide: str = field(repr=False)
    content_hash: str = ""


@dataclass(frozen=True)
class PersonalStyleCollection:
    profiles: tuple[PersonalStyleProfile, ...] = ()
    selected_profile_id: str = ""


@dataclass(frozen=True)
class PersonalStyleOption:
    profile_id: str
    name: str


@dataclass(frozen=True)
class PersonalStyleState:
    profiles: tuple[PersonalStyleOption, ...] = ()
    selected_profile_id: str = ""
    operation_state: SettingsOperationState = "idle"
    operation_kind: Literal["import", "select"] | None = None
    operation_id: str = ""
    message: str = ""


@dataclass(frozen=True)
class ModelCatalogConnection:
    """Explicit, in-memory connection values for a model-catalog refresh."""

    base_url: str = field(default="", repr=False)
    api_key: str = field(default="", repr=False)
    fallback_model: str = ""


@dataclass(frozen=True)
class TextContent:
    text: str


@dataclass(frozen=True)
class ImageContent:
    data: bytes
    mime_type: str
    source: ImageSource = "clipboard"


MessageContent = str | tuple[TextContent | ImageContent, ...]


@dataclass(frozen=True)
class LLMMessage:
    role: MessageRole
    content: MessageContent


@dataclass(frozen=True)
class LLMRequest:
    messages: tuple[LLMMessage, ...]
    model: str
    temperature: float


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class UserFacingError:
    message: str
    suggestion: str = ""


@dataclass(frozen=True)
class OutputOperationIntent:
    operation_id: str
    workflow_id: str
    kind: OutputActionKind
    text: str


@dataclass(frozen=True)
class OutputOperationResult:
    operation_id: str
    workflow_id: str
    kind: OutputActionKind
    state: OutputOperationState
    error: UserFacingError | None = None
    message: str = ""
    reason: PasteFailureReason | None = None

    def __post_init__(self) -> None:
        common_states = {"pending", "failed", "cancelled"}
        paste_states = common_states | {"dispatched_unconfirmed", "cleanup_failed"}
        allowed = paste_states if self.kind == "paste" else common_states | {"succeeded"}
        if self.state not in allowed:
            raise ValueError(
                f"unsupported {self.kind} output-operation state: {self.state}"
            )


@dataclass(frozen=True)
class LLMResult:
    text: str
    provider: str
    model: str
    finish_reason: str | None = None
    usage: LLMUsage | None = None


@dataclass(frozen=True)
class LLMTextDelta:
    text: str


@dataclass(frozen=True)
class LLMCompleted:
    result: LLMResult


LLMProviderEvent = LLMTextDelta | LLMCompleted


@dataclass(frozen=True)
class FeedbackReason:
    id: str
    label: str


@dataclass(frozen=True)
class ActionFeedbackContract:
    ai_help_label: str
    ai_does_not_label: str
    reasons: tuple[FeedbackReason, ...]


@dataclass(frozen=True)
class ActionFeedbackRecord:
    record_schema_version: int
    feedback_id: str
    created_at: str
    workflow_id: str
    step_id: str
    action_id: str
    action_version: str
    press_type: PressType
    provider: str
    model: str
    input_source: str
    outcome: FeedbackOutcome
    reason: str = ""
    note: str = ""
    input_text: str | None = None
    result_text: str | None = None


@dataclass(frozen=True)
class ActionVariant:
    name: str
    system_prompt: str
    prompt: str
    output_profile: str | None = None
    feedback_contract: ActionFeedbackContract | None = None


@dataclass(frozen=True)
class ActionDefinition:
    id: str
    name: str
    system_prompt: str
    prompt: str
    press_variants: dict[PressType, ActionVariant]
    stream: bool | None = None
    input_mode: InputMode = "selection_or_clipboard"
    output_mode: OutputMode = "popup"
    temperature: float | None = None
    output_profile: str = "plain_text"
    external_fallback: ExternalFallback = "selection_or_clipboard"
    feedback_contract: ActionFeedbackContract | None = None
    personal_style_mode: PersonalStyleMode | None = None


@dataclass(frozen=True)
class ShortcutDefinition:
    id: str
    hotkey: str
    command: ShortcutCommandKind
    action_id: str | None = None


@dataclass(frozen=True)
class ShortcutGuideItem:
    shortcut_id: str
    hotkey: str
    display_hotkey: str
    key_tokens: frozenset[str]
    title: str
    short_description: str
    long_title: str = ""
    long_description: str = ""


@dataclass(frozen=True)
class ShortcutGuideSnapshot:
    guide_id: str
    items: tuple[ShortcutGuideItem, ...]
    selected_shortcut_id: str
    pressed_keys: frozenset[str] = frozenset()
    verified: frozenset[tuple[str, PressType]] = frozenset()
    phase: ShortcutGuidePhase = "listening"
    status_text: str = "請按住快捷鍵組合，再按一個功能鍵。"
    matched_shortcut_id: str = ""
    matched_press_type: PressType | None = None


@dataclass(frozen=True)
class SpeechRequest:
    text: str
    voice_override: str | None
    cancellation: CancellationToken
    rate_override: str | None = None


@dataclass(frozen=True)
class ResolvedAction:
    id: str
    name: str
    system_prompt: str
    prompt: str
    press_type: PressType
    input_mode: InputMode
    output_mode: OutputMode
    temperature: float | None
    output_profile: str = "plain_text"
    external_fallback: ExternalFallback = "selection_or_clipboard"
    feedback_contract: ActionFeedbackContract | None = None
    version_id: str = ""
    stream: bool = False
    personal_style_mode: PersonalStyleMode | None = None
    personal_style: PersonalStyleProfile | None = None


@dataclass(frozen=True)
class InputTarget:
    kind: Literal["external_text", "workflow_result"]
    document: InputDocument | None = None


@dataclass(frozen=True)
class ActionInvocation:
    invocation_id: str
    action_id: str
    press_type: PressType
    input_target: InputTarget
    result_route: ResultRoute = "popup"
    workflow_id: str | None = None
    parent_step_id: str | None = None


@dataclass(frozen=True)
class WorkflowStep:
    step_id: str
    action_id: str
    title: str
    input_text: str
    result_text: str
    output_profile: str
    parent_step_id: str | None = None
    press_type: PressType = "short"
    presentation: PresentationDocument | None = None
    input_source: str = ""
    feedback_contract: ActionFeedbackContract | None = None
    action_version: str = ""
    provider: str = ""
    model: str = ""


@dataclass(frozen=True)
class GuidancePreferences:
    first_use_hints_enabled: bool = False
    seen_action_ids: frozenset[str] = frozenset()
    update_pending: bool = False


@dataclass(frozen=True)
class UserPreferences:
    first_use_hints_enabled: bool = False
    seen_action_ids: frozenset[str] = frozenset()
    speech_speed: SpeechSpeed | None = None
    voice_input_enabled: bool = False
    voice_language: VoiceLanguagePreference = "zh-TW"


@dataclass(frozen=True)
class ActiveWorkflowContext:
    workflow_id: str
    step_id: str
    content: str
    selected_text: str | None = None


@dataclass(frozen=True)
class OutputProfile:
    id: str
    instruction: str
    required_markers: tuple[str, ...] = ()
    presentation: str = "plain_text"


@dataclass(frozen=True)
class InputDocument:
    text: str
    source: Literal["selection", "clipboard", "workflow_result", "voice_draft", "voice_transcript", "screenshot"]
    workflow_id: str | None = None
    step_id: str | None = None
    image: ImageContent | None = None


@dataclass(frozen=True)
class SelectionCaptureOutcome:
    text: str = ""
    status: Literal["captured", "empty", "modifier_timeout", "cancelled", "failed"] = "empty"


@dataclass(frozen=True)
class PasteTarget:
    """Opaque snapshot of a non-ClipAI window that can receive paste output."""

    window_token: str
    process_id: int
    application_name: str
    window_title: str
    observation_sequence: int


@dataclass(frozen=True)
class WorkflowAttention:
    """A transient request to surface an existing Workflow to the user."""

    attention_id: str
    workflow_id: str
    message: str
    duration_ms: int = 3000
    request_focus: bool = True
    warning: bool = True


@dataclass(frozen=True)
class PasteRequest:
    operation_id: str
    workflow_id: str
    text: str
    target: PasteTarget


@dataclass(frozen=True)
class PasteDispatchReceipt:
    state: Literal["dispatched_unconfirmed"]
    detail: str = ""


@dataclass(frozen=True)
class PasteOutcome:
    state: PasteCompletionState
    delivery: PasteDeliveryState
    cleanup: PasteCleanupState
    message: str = ""
    reason: PasteFailureReason | None = None


@dataclass(frozen=True)
class ProcessedResult:
    text: str
    output_profile: str = "plain_text"
    presentation: str = "plain_text"
    document: PresentationDocument | None = None


@dataclass(frozen=True)
class InlineSpan:
    text: str
    style: InlineStyle = "plain"
    canonical_text: str | None = None


@dataclass(frozen=True)
class PresentationBlock:
    kind: PresentationBlockKind
    spans: tuple[InlineSpan, ...]
    level: int = 0
    ordinal: int | None = None
    canonical_prefix: str = ""


@dataclass(frozen=True)
class PresentationDocument:
    blocks: tuple[PresentationBlock, ...]
    fallback_text: str


@dataclass(frozen=True)
class ReadinessIssue:
    code: str
    message: str
    feature: str


@dataclass(frozen=True)
class DisplayMetrics:
    scale: float
    work_x: int
    work_y: int
    work_width: int
    work_height: int
    cursor_x: int
    cursor_y: int


@dataclass(frozen=True)
class PopupBounds:
    x: int
    y: int
    width: int
    height: int
