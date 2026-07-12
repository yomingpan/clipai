from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ClipAI.core.state import CancellationToken

PressType = Literal["short", "long"]
MessageRole = Literal["system", "user", "assistant"]
InputMode = Literal["clipboard", "selection_or_clipboard"]
OutputMode = Literal["popup"]
InputPolicy = Literal["external_text", "contextual_text"]
ResultRoute = Literal["popup", "speech"]
ApplicationStatus = Literal["idle", "processing", "success", "warning", "error", "paused"]
OperationKind = Literal["llm", "tts"]
ShortcutCommandKind = Literal["start_action", "speak_selection_or_clipboard"]


@dataclass(frozen=True)
class LLMMessage:
    role: MessageRole
    content: str


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
class LLMResult:
    text: str
    provider: str
    model: str
    finish_reason: str | None = None
    usage: LLMUsage | None = None


@dataclass(frozen=True)
class ActionVariant:
    name: str
    system_prompt: str
    prompt: str
    output_profile: str | None = None


@dataclass(frozen=True)
class ActionDefinition:
    id: str
    name: str
    system_prompt: str
    prompt: str
    press_variants: dict[PressType, ActionVariant]
    stream: bool = False
    input_mode: InputMode = "clipboard"
    output_mode: OutputMode = "popup"
    temperature: float | None = None
    output_profile: str = "plain_text"
    input_policy: InputPolicy = "external_text"


@dataclass(frozen=True)
class ShortcutDefinition:
    id: str
    hotkey: str
    command: ShortcutCommandKind
    action_id: str | None = None


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
    input_policy: InputPolicy = "external_text"


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


@dataclass(frozen=True)
class ProcessedResult:
    text: str
    output_profile: str = "plain_text"
    presentation: str = "plain_text"


@dataclass(frozen=True)
class ReadinessIssue:
    code: str
    message: str
    feature: str
