from __future__ import annotations

import threading
from dataclasses import dataclass


class LLMCancelledError(Exception):
    """Raised when cooperative cancellation is requested."""


@dataclass(frozen=True)
class CancellationToken:
    _event: threading.Event

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def throw_if_cancelled(self) -> None:
        if self.is_cancelled():
            raise LLMCancelledError("operation cancelled")


class CancellationController:
    def __init__(self) -> None:
        self._event = threading.Event()
        self._reason: str | None = None

    @property
    def token(self) -> CancellationToken:
        return CancellationToken(self._event)

    @property
    def reason(self) -> str | None:
        return self._reason

    def cancel(self, reason: str | None = None) -> None:
        self._reason = reason
        self._event.set()
