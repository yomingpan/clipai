from __future__ import annotations

import threading
from dataclasses import dataclass

from ClipAI.core.errors import PASTE_FAILURE_MESSAGES, PasteFailure
from ClipAI.core.models import InterruptibleOperationRef, OutputActionKind, OutputOperationIntent, OutputOperationResult, PasteOutcome, UserFacingError
from ClipAI.core.ports import OperationHandle, OperationTracker, OutputOperationPresenter
from ClipAI.services.user_control import InterruptibleOperationLease, UserControlCoordinator


@dataclass(frozen=True)
class _ActiveOutputOperation:
    intent: OutputOperationIntent
    handle: OperationHandle | None
    lease: InterruptibleOperationLease | None


class OutputOperationCoordinator:
    """Own output identity, terminal acknowledgement, tracker, and interruption lease."""

    def __init__(self, presenter: OutputOperationPresenter, tracker: OperationTracker | None = None) -> None:
        self._presenter = presenter
        self._tracker = tracker
        self._user_control: UserControlCoordinator | None = None
        self._active: dict[tuple[str, str], _ActiveOutputOperation] = {}
        self._lock = threading.RLock()

    def bind_user_control(self, user_control: UserControlCoordinator) -> None:
        self._user_control = user_control

    def begin(self, intent: OutputOperationIntent) -> None:
        tracker_kind = "tts" if intent.kind == "speech" else intent.kind
        handle = self._tracker.start(f"{tracker_kind}:{intent.operation_id}", tracker_kind) if self._tracker else None
        lease = self._user_control.begin(InterruptibleOperationRef(
            intent.operation_id,
            intent.kind,
            workflow_id=intent.workflow_id,
            surface_id=intent.workflow_id if intent.workflow_id != "global" else "",
        )) if self._user_control is not None else None
        record = _ActiveOutputOperation(intent, handle, lease)
        key = (intent.workflow_id, intent.kind)
        with self._lock:
            previous = self._active.pop(key, None)
            self._active[key] = record
        try:
            self._release(previous, "cancelled")
        except BaseException:
            with self._lock:
                if self._active.get(key) is record:
                    self._active.pop(key, None)
            self._release(record, "cancelled")
            raise
        self._presenter.present_output_operation(
            OutputOperationResult(intent.operation_id, intent.workflow_id, intent.kind, "pending")
        )

    def settle(self, result: OutputOperationResult) -> bool:
        if result.state == "pending":
            raise ValueError("pending output-operation state belongs to begin()")
        key = (result.workflow_id, result.kind)
        with self._lock:
            record = self._active.get(key)
            if record is None or record.intent.operation_id != result.operation_id:
                return False
            self._active.pop(key, None)
        release_error: BaseException | None = None
        try:
            self._release(record, result.state)
        except BaseException as exc:
            release_error = exc
        self._presenter.present_output_operation(result)
        if release_error is not None:
            raise release_error
        return True

    def active_intent(
        self,
        operation_id: str,
        workflow_id: str,
        kind: OutputActionKind,
    ) -> OutputOperationIntent | None:
        with self._lock:
            record = self._active.get((workflow_id, kind))
            if record is None or record.intent.operation_id != operation_id:
                return None
            return record.intent

    def fail(self, intent: OutputOperationIntent, error: BaseException) -> bool:
        if intent.kind == "paste" and not isinstance(error, PasteFailure):
            error = PasteFailure("unknown", PASTE_FAILURE_MESSAGES["unknown"])
        reason = (
            error.reason
            if intent.kind == "paste" and isinstance(error, PasteFailure)
            else None
        )
        return self.settle(OutputOperationResult(
            intent.operation_id,
            intent.workflow_id,
            intent.kind,
            "failed",
            UserFacingError(str(error), "Try again or open diagnostics if the problem continues."),
            reason=reason,
        ))

    def cancel_operation(self, operation_id: str) -> OutputOperationIntent | None:
        with self._lock:
            record = next((value for value in self._active.values() if value.intent.operation_id == operation_id), None)
        if record is None:
            return None
        self.settle(OutputOperationResult(operation_id, record.intent.workflow_id, record.intent.kind, "cancelled"))
        return record.intent

    def cancel_all(self, *, exclude_operation_ids: frozenset[str] = frozenset()) -> tuple[OutputOperationIntent, ...]:
        with self._lock:
            records = tuple(record for record in self._active.values() if record.intent.operation_id not in exclude_operation_ids)
        first_error: BaseException | None = None
        for record in records:
            try:
                self.settle(OutputOperationResult(
                    record.intent.operation_id,
                    record.intent.workflow_id,
                    record.intent.kind,
                    "cancelled",
                ))
            except BaseException as exc:
                first_error = first_error or exc
        if first_error is not None:
            raise first_error
        return tuple(record.intent for record in records)

    @staticmethod
    def _release(record: _ActiveOutputOperation | None, state: str) -> None:
        if record is None:
            return
        try:
            if record.handle is not None:
                if state in {"succeeded", "dispatched_unconfirmed"}:
                    record.handle.succeed()
                elif state in {"failed", "cleanup_failed"}:
                    record.handle.fail()
                else:
                    record.handle.cancel()
        finally:
            if record.lease is not None:
                record.lease.finish()


def paste_outcome_result(intent: OutputOperationIntent, outcome: PasteOutcome) -> OutputOperationResult:
    if intent.kind != "paste":
        raise ValueError("Paste outcome requires a Paste Operation intent")
    if outcome.state == "failed":
        return OutputOperationResult(
            intent.operation_id,
            intent.workflow_id,
            "paste",
            "failed",
            UserFacingError(outcome.message, "Try again or open diagnostics if the problem continues."),
            reason=outcome.reason,
        )
    return OutputOperationResult(
        intent.operation_id,
        intent.workflow_id,
        "paste",
        outcome.state,
        message=outcome.message,
        reason=outcome.reason,
    )
