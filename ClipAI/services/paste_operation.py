from __future__ import annotations

import threading

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
    ) -> None:
        self._clipboard_transactions = clipboard_transactions
        self._dispatcher = dispatcher
        self._active_by_workflow: dict[str, PasteOperation] = {}
        self._lock = threading.RLock()

    def create(self, request: PasteRequest) -> PasteOperation:
        operation = PasteOperation(self, request)
        with self._lock:
            previous = self._active_by_workflow.get(request.workflow_id)
            if previous is not None and not previous.cancel():
                raise PasteOperationInProgress(
                    "A Paste Operation for this Workflow is already running."
                )
            self._active_by_workflow[request.workflow_id] = operation
        return operation

    def _execute(self, operation: PasteOperation) -> PasteOutcome:
        request = operation.request
        transaction = self._clipboard_transactions.use_temporary_text(
            request.operation_id,
            request.text,
            lambda: self._dispatcher.dispatch(request.target, operation.cancellation),
            operation.cancellation,
        )
        return _paste_outcome(transaction)

    def _release(self, operation: PasteOperation) -> None:
        with self._lock:
            if self._active_by_workflow.get(operation.request.workflow_id) is operation:
                self._active_by_workflow.pop(operation.request.workflow_id, None)


class PasteOperation:
    def __init__(self, coordinator: PasteOperationCoordinator, request: PasteRequest) -> None:
        self._coordinator = coordinator
        self.request = request
        self.cancellation = CancellationToken()
        self._run_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._running = False
        self._outcome: PasteOutcome | None = None

    def cancel(self) -> bool:
        self.cancellation.cancel()
        with self._state_lock:
            return not self._running

    def run(self) -> PasteOutcome:
        with self._run_lock:
            with self._state_lock:
                if self._outcome is not None:
                    return self._outcome
                self._running = True
            try:
                outcome = self._coordinator._execute(self)
            except BaseException:
                with self._state_lock:
                    self._running = False
                raise
            finally:
                self._coordinator._release(self)
            with self._state_lock:
                self._outcome = outcome
                self._running = False
                return outcome


class PasteOperationInProgress(RuntimeError):
    pass


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
