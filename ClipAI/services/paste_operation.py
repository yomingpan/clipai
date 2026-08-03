from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import threading
from typing import Literal

from ClipAI.core.commands import PasteOperationCompleted
from ClipAI.core.errors import CancelledError
from ClipAI.core.models import PasteDispatchReceipt, PasteOutcome, PasteRequest
from ClipAI.core.ports import TargetedPasteOutput
from ClipAI.core.state import CancellationToken
from ClipAI.services.clipboard_transaction import ClipboardTransactionCoordinator, TemporaryTextResult


class PasteOperationCoordinator:
    """Own Paste identity, cancellation, commit truth, and clipboard cleanup outcome."""

    def __init__(
        self,
        *,
        clipboard_transactions: ClipboardTransactionCoordinator,
        dispatcher: TargetedPasteOutput,
        completion_sink: Callable[[PasteOperationCompleted], None],
    ) -> None:
        self._clipboard_transactions = clipboard_transactions
        self._dispatcher = dispatcher
        self._completion_sink = completion_sink
        self._active: _ActivePaste | None = None
        self._lock = threading.RLock()

    def admit(self, request: PasteRequest) -> bool:
        with self._lock:
            if self._active is not None:
                rejected = PasteOperationCompleted(
                    request.operation_id,
                    request.workflow_id,
                    PasteOutcome(
                        "failed",
                        "not_dispatched",
                        "not_required",
                        "Another Paste Operation is still in progress.",
                    ),
                )
            else:
                self._active = _ActivePaste(request)
                rejected = None
        if rejected is not None:
            self._completion_sink(rejected)
            return False
        return True

    def execute(self, operation_id: str) -> None:
        with self._lock:
            active = self._matching_active(operation_id)
            if active is None or active.state != "admitted":
                return
            active.state = "running"
        request = active.request
        try:
            transaction = self._clipboard_transactions.use_temporary_text(
                request.operation_id,
                request.text,
                lambda: self._dispatcher.dispatch(request.target, active.cancellation),
                active.cancellation,
            )
            outcome = _paste_outcome(transaction)
        except BaseException as exc:
            self._finish(
                active,
                PasteOutcome("failed", "not_dispatched", "not_required", str(exc)),
            )
            raise
        self._finish(active, outcome)

    def request_cancel(self, operation_id: str) -> bool:
        with self._lock:
            active = self._matching_active(operation_id)
            if active is None:
                return False
            active.cancellation.cancel()
            finish_queued = active.state == "admitted"
            if finish_queued:
                active.state = "finishing"
        if finish_queued:
            self._emit_and_release(
                active,
                PasteOutcome("cancelled", "not_dispatched", "not_required"),
            )
        return True

    def request_cancel_for_workflow(self, workflow_id: str) -> str | None:
        with self._lock:
            active = self._active
            operation_id = (
                active.request.operation_id
                if active is not None and active.request.workflow_id == workflow_id
                else None
            )
        if operation_id is not None:
            self.request_cancel(operation_id)
        return operation_id

    def request_cancel_active(self) -> str | None:
        with self._lock:
            operation_id = self._active.request.operation_id if self._active is not None else None
        if operation_id is not None:
            self.request_cancel(operation_id)
        return operation_id

    def fail_to_start(self, operation_id: str, error: BaseException) -> bool:
        with self._lock:
            active = self._matching_active(operation_id)
            if active is None or active.state != "admitted":
                return False
            active.state = "finishing"
        self._emit_and_release(
            active,
            PasteOutcome("failed", "not_dispatched", "not_required", str(error)),
        )
        return True

    def _finish(self, active: _ActivePaste, outcome: PasteOutcome) -> bool:
        with self._lock:
            if self._active is not active or active.state in {"finishing", "completed"}:
                return False
            active.state = "finishing"
        self._emit_and_release(active, outcome)
        return True

    def _emit_and_release(self, active: _ActivePaste, outcome: PasteOutcome) -> None:
        completion = PasteOperationCompleted(
            active.request.operation_id,
            active.request.workflow_id,
            outcome,
        )
        try:
            self._completion_sink(completion)
        finally:
            with self._lock:
                active.state = "completed"
                if self._active is active:
                    self._active = None

    def _matching_active(self, operation_id: str) -> _ActivePaste | None:
        active = self._active
        return active if active is not None and active.request.operation_id == operation_id else None


@dataclass
class _ActivePaste:
    request: PasteRequest
    cancellation: CancellationToken = field(default_factory=CancellationToken)
    state: Literal["admitted", "running", "finishing", "completed"] = "admitted"


def _paste_outcome(result: TemporaryTextResult[PasteDispatchReceipt]) -> PasteOutcome:
    delivery = result.value.state if result.value is not None else "not_dispatched"
    if result.cleanup == "failed":
        if delivery == "dispatched_unconfirmed":
            message = "Paste may already be pasted, but the previous clipboard content could not be restored. Confirm the target before trying again."
        else:
            message = "Paste was not dispatched, but ClipAI could not restore the previous clipboard content."
        return PasteOutcome("cleanup_failed", delivery, "failed", message)
    if result.value is not None:
        message = result.value.detail or "Paste command was sent, but the target application cannot confirm completion. Check the target before trying again."
        if result.cleanup == "external_change":
            message += " The clipboard changed externally, so ClipAI did not overwrite it."
        return PasteOutcome("dispatched_unconfirmed", delivery, result.cleanup, message)
    if result.cancelled or isinstance(result.error, CancelledError):
        return PasteOutcome("cancelled", "not_dispatched", result.cleanup)
    message = str(result.error) if result.error is not None else "Paste could not be dispatched."
    return PasteOutcome("failed", "not_dispatched", result.cleanup, message)
