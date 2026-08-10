from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ClipAI.core.models import ActionFeedbackContract, FeedbackOperationState, PresentationDocument, ResultCompleteness, WorkflowStep
    from ClipAI.core.voice import VoiceCaptureId, VoiceOrigin


class SessionStatus(str, Enum):
    CREATED = "created"
    READING_INPUT = "reading_input"
    PREPARING_REQUEST = "preparing_request"
    REQUESTING_PROVIDER = "requesting_provider"
    PROCESSING_RESULT = "processing_result"
    VOICE_PREPARING = "voice_preparing"
    VOICE_LISTENING = "voice_listening"
    VOICE_FINALIZING = "voice_finalizing"
    VOICE_REVIEW = "voice_review"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"
    CANCELLED = "cancelled"
    CLOSED = "closed"


TERMINAL_STATUSES = {
    SessionStatus.COMPLETED,
    SessionStatus.FAILED,
    SessionStatus.STOPPED,
    SessionStatus.CANCELLED,
    SessionStatus.CLOSED,
}

ALLOWED_TRANSITIONS: dict[SessionStatus, set[SessionStatus]] = {
    SessionStatus.CREATED: {SessionStatus.READING_INPUT, SessionStatus.VOICE_PREPARING, SessionStatus.STOPPED, SessionStatus.CANCELLED, SessionStatus.CLOSED},
    SessionStatus.READING_INPUT: {SessionStatus.PREPARING_REQUEST, SessionStatus.VOICE_PREPARING, SessionStatus.FAILED, SessionStatus.STOPPED, SessionStatus.CANCELLED, SessionStatus.CLOSED},
    SessionStatus.PREPARING_REQUEST: {SessionStatus.REQUESTING_PROVIDER, SessionStatus.VOICE_PREPARING, SessionStatus.FAILED, SessionStatus.STOPPED, SessionStatus.CANCELLED, SessionStatus.CLOSED},
    SessionStatus.REQUESTING_PROVIDER: {SessionStatus.PROCESSING_RESULT, SessionStatus.VOICE_PREPARING, SessionStatus.FAILED, SessionStatus.STOPPED, SessionStatus.CANCELLED, SessionStatus.CLOSED},
    SessionStatus.PROCESSING_RESULT: {SessionStatus.COMPLETED, SessionStatus.VOICE_PREPARING, SessionStatus.FAILED, SessionStatus.STOPPED, SessionStatus.CANCELLED, SessionStatus.CLOSED},
    SessionStatus.COMPLETED: {SessionStatus.PREPARING_REQUEST, SessionStatus.VOICE_PREPARING, SessionStatus.CLOSED},
    SessionStatus.VOICE_PREPARING: {SessionStatus.VOICE_LISTENING, SessionStatus.VOICE_FINALIZING, SessionStatus.VOICE_REVIEW, SessionStatus.CLOSED},
    SessionStatus.VOICE_LISTENING: {SessionStatus.VOICE_FINALIZING, SessionStatus.VOICE_REVIEW, SessionStatus.CLOSED},
    SessionStatus.VOICE_FINALIZING: {SessionStatus.VOICE_REVIEW, SessionStatus.CLOSED},
    SessionStatus.VOICE_REVIEW: {SessionStatus.VOICE_PREPARING, SessionStatus.CLOSED},
    SessionStatus.FAILED: {SessionStatus.VOICE_PREPARING, SessionStatus.CLOSED},
    SessionStatus.STOPPED: {SessionStatus.VOICE_PREPARING, SessionStatus.CLOSED},
    SessionStatus.CANCELLED: {SessionStatus.VOICE_PREPARING, SessionStatus.CLOSED},
    SessionStatus.CLOSED: set(),
}


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()


@dataclass(frozen=True)
class SessionSnapshot:
    session_id: str
    revision: int
    status: SessionStatus
    action_id: str
    title: str
    model: str
    source_preview: str = "Hotkey received"
    status_text: str = "Hotkey received"
    content: str = ""
    error: str = ""
    pinned: bool = False
    available_actions: tuple[str, ...] = ()
    original_input: str = ""
    speaking: bool = False
    steps: tuple[WorkflowStep, ...] = ()
    displayed_step_index: int = -1
    active_invocation_id: str | None = None
    can_navigate_back: bool = False
    presentation: PresentationDocument | None = None
    action_feedback_contract: ActionFeedbackContract | None = None
    input_source: str = ""
    feedback_state: FeedbackOperationState = "idle"
    feedback_step_id: str = ""
    feedback_operation_id: str = ""
    feedback_message: str = ""
    show_guidance_hint: bool = False
    result_completeness: ResultCompleteness = "none"
    voice_origin: VoiceOrigin | None = None
    voice_capture_id: VoiceCaptureId | None = None

    def evolve(self, **changes: object) -> SessionSnapshot:
        return replace(self, revision=self.revision + 1, **changes)
