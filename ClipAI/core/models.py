from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PressType = Literal["short", "long"]
MessageRole = Literal["system", "user", "assistant"]
InputMode = Literal["clipboard", "selection_or_clipboard"]
OutputMode = Literal["popup"]


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


@dataclass(frozen=True)
class ActionDefinition:
    id: str
    name: str
    hotkey: str
    system_prompt: str
    prompt: str
    press_variants: dict[PressType, ActionVariant]
    stream: bool = False
    input_mode: InputMode = "clipboard"
    output_mode: OutputMode = "popup"
    temperature: float | None = None


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


@dataclass(frozen=True)
class InputDocument:
    text: str
    source: Literal["selection", "clipboard"]


@dataclass(frozen=True)
class ProcessedResult:
    text: str

