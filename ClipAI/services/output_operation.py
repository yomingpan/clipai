from __future__ import annotations

import threading
from collections.abc import Callable

from ClipAI.core.models import OutputOperationIntent, OutputOperationResult, OutputOperationState, UserFacingError
from ClipAI.core.ports import OperationHandle, OperationTracker, OutputOperationPresenter


class OutputOperationCoordinator:
    """Own output-operation identity and reject stale terminal projections."""

    def __init__(self, presenter: OutputOperationPresenter, tracker: OperationTracker | None = None) -> None:
        self._presenter = presenter
        self._tracker = tracker
        self._active: dict[tuple[str, str], tuple[OutputOperationIntent, OperationHandle | None]] = {}
        self._lock = threading.RLock()

    def begin(self, intent: OutputOperationIntent) -> OperationHandle | None:
        key = (intent.workflow_id, intent.kind)
        tracker_kind = "tts" if intent.kind == "speech" else intent.kind
        handle = self._tracker.start(f"{tracker_kind}:{intent.operation_id}", tracker_kind) if self._tracker else None
        with self._lock:
            previous = self._active.get(key)
            self._active[key] = (intent, handle)
        if previous is not None and previous[1] is not None:
            previous[1].cancel()
        self._presenter.present_output_operation(
            OutputOperationResult(intent.operation_id, intent.workflow_id, intent.kind, "pending")
        )
        return handle

    def cancel_all(self, *, exclude_operation_ids: frozenset[str] = frozenset()) -> tuple[OutputOperationIntent, ...]:
        with self._lock:
            active = tuple(
                value
                for value in self._active.values()
                if value[0].operation_id not in exclude_operation_ids
            )
            self._active = {
                key: value
                for key, value in self._active.items()
                if value[0].operation_id in exclude_operation_ids
            }
        for intent, handle in active:
            if handle is not None:
                handle.cancel()
            self._presenter.present_output_operation(
                OutputOperationResult(intent.operation_id, intent.workflow_id, intent.kind, "cancelled")
            )
        return tuple(intent for intent, _handle in active)

    def cancel_operation(self, operation_id: str) -> OutputOperationIntent | None:
        with self._lock:
            match = next(
                (
                    (key, intent, handle)
                    for key, (intent, handle) in self._active.items()
                    if intent.operation_id == operation_id
                ),
                None,
            )
            if match is None:
                return None
            key, intent, handle = match
            self._active.pop(key, None)
        if handle is not None:
            handle.cancel()
        self._presenter.present_output_operation(
            OutputOperationResult(intent.operation_id, intent.workflow_id, intent.kind, "cancelled")
        )
        return intent

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

    def warn(
        self,
        intent: OutputOperationIntent,
        state: OutputOperationState,
        message: str,
        handle: OperationHandle | None = None,
    ) -> bool:
        if intent.kind != "paste" or state not in {"dispatched_unconfirmed", "cleanup_failed"}:
            raise ValueError(f"unsupported output warning state: {state}")
        if handle is not None:
            if state == "cleanup_failed":
                handle.fail()
            else:
                handle.succeed()
        return self._finish(intent, state, message=message)

    def run(self, intent: OutputOperationIntent, work: Callable[[], None]) -> None:
        handle = self.begin(intent)
        try:
            work()
        except BaseException as exc:
            self.fail(intent, exc, handle)
            raise
        self.succeed(intent, handle)

    def _finish(
        self,
        intent: OutputOperationIntent,
        state: OutputOperationState,
        error: UserFacingError | None = None,
        message: str = "",
    ) -> bool:
        key = (intent.workflow_id, intent.kind)
        with self._lock:
            active = self._active.get(key)
            if active is None or active[0].operation_id != intent.operation_id:
                return False
            self._active.pop(key, None)
        self._presenter.present_output_operation(
            OutputOperationResult(intent.operation_id, intent.workflow_id, intent.kind, state, error, message)
        )
        return True
