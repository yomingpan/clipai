from __future__ import annotations

import threading

from ClipAI.core.ports import ResultPresenter
from ClipAI.core.state import ALLOWED_TRANSITIONS, CancellationToken, SessionSnapshot, SessionStatus, TERMINAL_STATUSES


class SessionController:
    """The only owner allowed to mutate one session's state."""

    def __init__(self, initial: SessionSnapshot, presenter: ResultPresenter) -> None:
        self._snapshot = initial
        self._presenter = presenter
        self._lock = threading.RLock()
        self.cancellation = CancellationToken()
        self._presenter.render(initial)

    @property
    def snapshot(self) -> SessionSnapshot:
        with self._lock:
            return self._snapshot

    @property
    def accepts_work(self) -> bool:
        with self._lock:
            return self._snapshot.status not in TERMINAL_STATUSES and not self.cancellation.is_cancelled

    def transition(self, status: SessionStatus, **changes: object) -> SessionSnapshot | None:
        with self._lock:
            current = self._snapshot.status
            if self.cancellation.is_cancelled and status not in {SessionStatus.CANCELLED, SessionStatus.CLOSED}:
                return None
            if status not in ALLOWED_TRANSITIONS[current]:
                return None
            self._snapshot = self._snapshot.evolve(status=status, **changes)
            snapshot = self._snapshot
        self._presenter.render(snapshot)
        return snapshot

    def fail(self, message: str) -> SessionSnapshot | None:
        return self.transition(SessionStatus.FAILED, status_text="Failed", error=message, available_actions=())

    def cancel(self) -> SessionSnapshot | None:
        self.cancellation.cancel()
        with self._lock:
            if self._snapshot.status in TERMINAL_STATUSES:
                return None
        return self.transition(SessionStatus.CANCELLED, status_text="Cancelled", available_actions=())

    def close(self) -> SessionSnapshot | None:
        self.cancellation.cancel()
        return self.transition(SessionStatus.CLOSED, status_text="Closed", available_actions=())

    def toggle_pin(self) -> SessionSnapshot:
        with self._lock:
            self._snapshot = self._snapshot.evolve(pinned=not self._snapshot.pinned)
            snapshot = self._snapshot
        self._presenter.render(snapshot)
        return snapshot

