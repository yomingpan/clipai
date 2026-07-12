from __future__ import annotations

import threading
from collections.abc import Callable

from ClipAI.core.models import OutputOperationIntent, OutputOperationResult, UserFacingError
from ClipAI.core.ports import OperationHandle, OperationTracker, OutputOperationPresenter


class OutputOperationCoordinator:
    """Own output-operation identity and reject stale terminal projections."""

    def __init__(self, presenter: OutputOperationPresenter, tracker: OperationTracker | None = None) -> None:
        self._presenter = presenter
        self._tracker = tracker
        self._active: dict[tuple[str, str], tuple[str, OperationHandle | None]] = {}
        self._lock = threading.RLock()

    def begin(self, intent: OutputOperationIntent) -> OperationHandle | None:
        key = (intent.workflow_id, intent.kind)
        tracker_kind = "tts" if intent.kind == "speech" else intent.kind
        handle = self._tracker.start(f"{tracker_kind}:{intent.operation_id}", tracker_kind) if self._tracker else None
        with self._lock:
            previous = self._active.get(key)
            self._active[key] = (intent.operation_id, handle)
        if previous is not None and previous[1] is not None:
            previous[1].cancel()
        self._presenter.present_output_operation(
            OutputOperationResult(intent.operation_id, intent.workflow_id, intent.kind, "pending")
        )
        return handle

    def succeed(self, intent: OutputOperationIntent, handle: OperationHandle | None = None) -> bool:
        if handle is not None:
            handle.succeed()
        return self._finish(intent, "succeeded")

    def fail(self, intent: OutputOperationIntent, error: BaseException, handle: OperationHandle | None = None) -> bool:
        if handle is not None:
            handle.fail()
        return self._finish(
            intent,
            "failed",
            UserFacingError(str(error), "Try again or open diagnostics if the problem continues."),
        )

    def cancel(self, intent: OutputOperationIntent, handle: OperationHandle | None = None) -> bool:
        if handle is not None:
            handle.cancel()
        return self._finish(intent, "cancelled")

    def run(self, intent: OutputOperationIntent, work: Callable[[], None]) -> None:
        handle = self.begin(intent)
        try:
            work()
        except BaseException as exc:
            self.fail(intent, exc, handle)
            raise
        self.succeed(intent, handle)

    def _finish(self, intent: OutputOperationIntent, state: str, error: UserFacingError | None = None) -> bool:
        key = (intent.workflow_id, intent.kind)
        with self._lock:
            active = self._active.get(key)
            if active is None or active[0] != intent.operation_id:
                return False
            self._active.pop(key, None)
        self._presenter.present_output_operation(
            OutputOperationResult(intent.operation_id, intent.workflow_id, intent.kind, state, error)  # type: ignore[arg-type]
        )
        return True
