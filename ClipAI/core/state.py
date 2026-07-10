from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import threading


class SessionStatus(str, Enum):
    CREATED = "created"
    READING_INPUT = "reading_input"
    PREPARING_REQUEST = "preparing_request"
    REQUESTING_PROVIDER = "requesting_provider"
    PROCESSING_RESULT = "processing_result"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    CLOSED = "closed"


TERMINAL_STATUSES = {
    SessionStatus.COMPLETED,
    SessionStatus.FAILED,
    SessionStatus.CANCELLED,
    SessionStatus.CLOSED,
}

ALLOWED_TRANSITIONS: dict[SessionStatus, set[SessionStatus]] = {
    SessionStatus.CREATED: {SessionStatus.READING_INPUT, SessionStatus.CANCELLED, SessionStatus.CLOSED},
    SessionStatus.READING_INPUT: {SessionStatus.PREPARING_REQUEST, SessionStatus.FAILED, SessionStatus.CANCELLED, SessionStatus.CLOSED},
    SessionStatus.PREPARING_REQUEST: {SessionStatus.REQUESTING_PROVIDER, SessionStatus.FAILED, SessionStatus.CANCELLED, SessionStatus.CLOSED},
    SessionStatus.REQUESTING_PROVIDER: {SessionStatus.PROCESSING_RESULT, SessionStatus.FAILED, SessionStatus.CANCELLED, SessionStatus.CLOSED},
    SessionStatus.PROCESSING_RESULT: {SessionStatus.COMPLETED, SessionStatus.FAILED, SessionStatus.CANCELLED, SessionStatus.CLOSED},
    SessionStatus.COMPLETED: {SessionStatus.PREPARING_REQUEST, SessionStatus.CLOSED},
    SessionStatus.FAILED: {SessionStatus.CLOSED},
    SessionStatus.CANCELLED: {SessionStatus.CLOSED},
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

    def evolve(self, **changes: object) -> SessionSnapshot:
        return replace(self, revision=self.revision + 1, **changes)
