from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ClipAI.core.state import CancellationToken

PressType = Literal["short", "long"]
HotkeyEventType = Literal["short", "long", "long_release", "invalid", "cancel"]
ShortcutGuidePhase = Literal["listening", "keys_pressed", "recognized", "invalid"]
MessageRole = Literal["system", "user", "assistant"]
ImageSource = Literal["clipboard"]
InputMode = Literal["clipboard", "clipboard_image", "selection_or_clipboard"]
OutputMode = Literal["popup"]
ExternalFallback = Literal["selection_or_clipboard", "clipboard"]
ResultRoute = Literal["popup", "speech"]
ApplicationStatus = Literal["idle", "processing", "success", "warning", "error", "paused"]
OperationKind = Literal["llm", "tts", "copy", "paste", "archive"]
FeedbackOutcome = Literal["helpful", "needs_adjustment", "not_applicable"]
FeedbackOperationState = Literal["idle", "pending", "succeeded", "failed"]
PresentationBlockKind = Literal["paragraph", "heading", "unordered_item", "ordered_item"]
InlineStyle = Literal["plain", "bold", "italic"]
ShortcutCommandKind = Literal["start_action", "speak_selection_or_clipboard"]
OutputActionKind = Literal["copy", "paste", "archive", "speech"]
OutputOperationState = Literal["pending", "succeeded", "failed", "cancelled"]
SettingsOperationState = Literal["idle", "pending", "succeeded", "failed"]
ProviderSettingsOperationKind = Literal["save", "refresh"]


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


@dataclass(frozen=True)
class LLMResult:
    text: str
    provider: str
    model: str
    finish_reason: str | None = None
    usage: LLMUsage | None = None


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
    stream: bool = False
    input_mode: InputMode = "selection_or_clipboard"
    output_mode: OutputMode = "popup"
    temperature: float | None = None
    output_profile: str = "plain_text"
    external_fallback: ExternalFallback = "selection_or_clipboard"
    feedback_contract: ActionFeedbackContract | None = None


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
    source: Literal["selection", "clipboard", "workflow_result", "voice_transcript", "screenshot"]
    workflow_id: str | None = None
    step_id: str | None = None
    image: ImageContent | None = None


@dataclass(frozen=True)
class ClipboardSnapshot:
    text: str
    image: ImageContent | None = None


@dataclass(frozen=True)
class PasteTarget:
    """Opaque snapshot of a non-ClipAI window that can receive paste output."""

    window_token: str
    process_id: int
    application_name: str
    window_title: str
    observation_sequence: int


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


@dataclass(frozen=True)
class PresentationBlock:
    kind: PresentationBlockKind
    spans: tuple[InlineSpan, ...]
    level: int = 0
    ordinal: int | None = None


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
