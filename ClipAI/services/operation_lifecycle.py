from __future__ import annotations

from collections.abc import Callable
import threading
from typing import Protocol

from ClipAI.core.models import ApplicationStatus, OperationKind, UserFacingError
from ClipAI.core.ports import OperationHandle, StatusIndicator


class CancellableCall(Protocol):
    def cancel(self) -> None: ...


ScheduleCall = Callable[[float, Callable[[], None]], CancellableCall]


def _schedule_timer(delay: float, callback: Callable[[], None]) -> CancellableCall:
    timer = threading.Timer(delay, callback)
    timer.daemon = True
    timer.start()
    return timer


class _TrackedOperation(OperationHandle):
    def __init__(self, coordinator: OperationLifecycleCoordinator, operation_id: str) -> None:
        self._coordinator = coordinator
        self._operation_id = operation_id
        self._done = False
        self._lock = threading.Lock()

    def succeed(self) -> None:
        self._finish("success")

    def fail(self) -> None:
        self._finish("error")

    def cancel(self) -> None:
        self._finish("cancel")

    def _finish(self, outcome: str) -> None:
        with self._lock:
            if self._done:
                return
            self._done = True
        self._coordinator._finish(self._operation_id, self, outcome)


class OperationLifecycleCoordinator:
    """Projects concurrent external-operation lifecycles onto one status indicator."""

    def __init__(
        self,
        status_indicator: StatusIndicator,
        *,
        ready: bool = True,
        schedule: ScheduleCall = _schedule_timer,
        success_duration: float = 2.0,
        error_duration: float = 3.0,
    ) -> None:
        self._indicator = status_indicator
        self._ready = ready
        self._schedule = schedule
        self._success_duration = success_duration
        self._error_duration = error_duration
        self._active: dict[str, tuple[OperationKind, _TrackedOperation]] = {}
        self._reset_call: CancellableCall | None = None
        self._transient_status: ApplicationStatus | None = None
        self._generation = 0
        self._last_error: UserFacingError | None = None
        self._lock = threading.RLock()
        self._indicator.set_status(self._baseline_status())

    def start(self, operation_id: str, kind: OperationKind) -> OperationHandle:
        if not operation_id.strip():
            raise ValueError("operation_id must not be empty")
        if kind not in ("llm", "tts", "copy", "paste", "archive"):
            raise ValueError(f"Unsupported operation kind: {kind}")
        with self._lock:
            if operation_id in self._active:
                raise ValueError(f"Operation is already active: {operation_id}")
            if self._transient_status == "success":
                self._cancel_reset_locked()
            self._last_error = None
            handle = _TrackedOperation(self, operation_id)
            self._active[operation_id] = (kind, handle)
            if self._transient_status != "error":
                self._indicator.set_status("processing")
            return handle

    def set_ready(self, ready: bool) -> None:
        with self._lock:
            self._ready = ready
            if not self._active and self._reset_call is None:
                self._indicator.set_status(self._baseline_status())

    def stop(self) -> None:
        with self._lock:
            self._cancel_reset_locked()
            self._active.clear()
            self._indicator.set_status(self._baseline_status())

    @property
    def last_error(self) -> UserFacingError | None:
        return self._last_error

    def report_waiting(self) -> None:
        with self._lock:
            if self._transient_status != "error":
                self._indicator.set_status("processing")

    def report_error(self, message: str, suggestion: str = "") -> None:
        with self._lock:
            self._cancel_reset_locked()
            self._last_error = UserFacingError(message, suggestion)
            self._transient_status = "error"
            self._indicator.set_status("error")

    def _finish(self, operation_id: str, handle: _TrackedOperation, outcome: str) -> None:
        with self._lock:
            current = self._active.get(operation_id)
            if current is None or current[1] is not handle:
                return
            del self._active[operation_id]
            if self._transient_status == "error" and outcome == "cancel":
                return
            if outcome == "success":
                self._last_error = None
            self._cancel_reset_locked()

            if outcome == "cancel":
                self._indicator.set_status(self._project_status())
                return
            if outcome == "success" and self._active:
                self._indicator.set_status("processing")
                return

            status: ApplicationStatus = "success" if outcome == "success" else "error"
            if outcome == "error":
                self._last_error = self._last_error or UserFacingError("An operation failed.")
                self._transient_status = "error"
                self._indicator.set_status("error")
                return
            duration = self._success_duration
            self._transient_status = status
            self._indicator.set_status(status)
            self._schedule_reset_locked(duration)

    def _schedule_reset_locked(self, delay: float) -> None:
        self._generation += 1
        generation = self._generation

        def reset() -> None:
            with self._lock:
                if generation != self._generation:
                    return
                self._reset_call = None
                self._transient_status = None
                self._indicator.set_status(self._project_status())

        self._reset_call = self._schedule(delay, reset)

    def _cancel_reset_locked(self) -> None:
        self._generation += 1
        if self._reset_call is not None:
            self._reset_call.cancel()
            self._reset_call = None
        self._transient_status = None

    def _project_status(self) -> ApplicationStatus:
        return "processing" if self._active else self._baseline_status()

    def _baseline_status(self) -> ApplicationStatus:
        return "idle" if self._ready else "warning"
