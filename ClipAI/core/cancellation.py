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
        self._interruptibles: list[object] = []

    @property
    def token(self) -> CancellationToken:
        return CancellationToken(self._event)

    @property
    def reason(self) -> str | None:
        return self._reason

    def cancel(self, reason: str | None = None) -> None:
        self._reason = reason
        self._event.set()

    def set_cancel_event(self, reason: str | None = None) -> None:
        self.cancel(reason)

    def clear_cancel_event(self) -> None:
        self._reason = None
        self._event.clear()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def register_interruptible(self, obj: object) -> None:
        self._interruptibles.append(obj)

    def interrupt_active_action(self) -> None:
        for obj in list(self._interruptibles):
            interrupt = getattr(obj, "interrupt", None)
            if callable(interrupt):
                try:
                    interrupt()
                except Exception:
                    pass


_controller: CancellationController | None = None
_controller_lock = threading.Lock()


def get_cancellation_controller() -> CancellationController:
    global _controller
    with _controller_lock:
        if _controller is None:
            _controller = CancellationController()
        return _controller
