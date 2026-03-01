from __future__ import annotations

from typing import Any, TypedDict


class ActionStartEvent(TypedDict):
    action_id: str
    action_name: str
    mode: str
    ts: int


class ActionCompleteEvent(TypedDict):
    action_id: str
    summary: str
    duration_ms: int
    ts: int


class ActionErrorEvent(TypedDict):
    action_id: str
    error_type: str
    message: str
    ts: int


class PipelineUpdateEvent(TypedDict):
    content: str
    source_meta: dict[str, Any]
    action_id: str
    ts: int


class UIStatusEvent(TypedDict):
    status: str


class TTSStateEvent(TypedDict):
    is_speaking: bool
    phase: str


class RhythmUpdateEvent(TypedDict):
    tempo: float
    state: str
    metrics: dict[str, Any]


class RhythmModeChangeEvent(TypedDict):
    mode: str
    params: dict[str, Any]


class RhythmReminderEvent(TypedDict):
    reason: str
    state: str


class MemoryChangeEvent(TypedDict):
    manual_count: int
    auto_count: int


class FollowUpRequestEvent(TypedDict):
    text: str
    action_id: str
