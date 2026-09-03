from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import logging
import threading
from typing import Literal

from ClipAI.core.commands import PasteOperationCompleted
from ClipAI.core.errors import CancelledError, PASTE_FAILURE_MESSAGES, PasteFailure
from ClipAI.core.models import PasteDispatchReceipt, PasteOutcome, PasteRequest
from ClipAI.core.ports import TargetedPasteOutput
from ClipAI.core.state import CancellationToken
from ClipAI.services.clipboard_transaction import ClipboardTransactionCoordinator, TemporaryTextResult


logger = logging.getLogger("clipai.paste")


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
                failure = PasteFailure(
                    "another_paste_active",
                    PASTE_FAILURE_MESSAGES["another_paste_active"],
                )
                rejected = PasteOperationCompleted(
                    request.operation_id,
                    request.workflow_id,
                    PasteOutcome(
                        "failed",
                        "not_dispatched",
                        "not_required",
                        str(failure),
                        failure.reason,
                    ),
                )
            else:
                self._active = _ActivePaste(request)
                rejected = None
        if rejected is not None:
            logger.warning(
                "Paste trace stage=admitted state=rejected operation_id=%s "
                "workflow_id=%s target_window=%s target_process_id=%s reason=%s",
                request.operation_id,
                request.workflow_id,
                request.target.window_token,
                request.target.process_id,
                rejected.outcome.reason,
            )
            self._completion_sink(rejected)
            return False
        logger.info(
            "Paste trace stage=admitted state=accepted operation_id=%s "
            "workflow_id=%s target_window=%s target_process_id=%s",
            request.operation_id,
            request.workflow_id,
            request.target.window_token,
            request.target.process_id,
        )
        return True

    def execute(self, operation_id: str) -> None:
        with self._lock:
            active = self._matching_active(operation_id)
            if active is None or active.state != "admitted":
                return
            active.state = "running"
        request = active.request
        logger.info(
            "Paste trace stage=running operation_id=%s workflow_id=%s "
            "target_window=%s target_process_id=%s",
            request.operation_id,
            request.workflow_id,
            request.target.window_token,
            request.target.process_id,
        )
        try:
            transaction = self._clipboard_transactions.use_temporary_text(
                request.operation_id,
                request.text,
                lambda: self._dispatch(active),
                active.cancellation,
            )
            logger.info(
                "Paste trace stage=cleanup operation_id=%s workflow_id=%s "
                "cleanup=%s dispatch_receipt=%s cancelled=%s error_type=%s",
                request.operation_id,
                request.workflow_id,
                transaction.cleanup,
                transaction.value.state if transaction.value is not None else "none",
                transaction.cancelled,
                type(transaction.error).__name__ if transaction.error is not None else "none",
            )
            outcome = _paste_outcome(transaction)
        except BaseException as exc:
            logger.warning(
                "Paste trace stage=execution_error operation_id=%s workflow_id=%s "
                "error_type=%s",
                request.operation_id,
                request.workflow_id,
                type(exc).__name__,
            )
            failure = _paste_failure(exc)
            self._finish(
                active,
                PasteOutcome(
                    "failed",
                    "not_dispatched",
                    "not_required",
                    str(failure),
                    failure.reason,
                ),
            )
            raise
        self._finish(active, outcome)

    def _dispatch(self, active: _ActivePaste) -> PasteDispatchReceipt:
        request = active.request
        logger.info(
            "Paste trace stage=dispatch_started operation_id=%s workflow_id=%s "
            "target_window=%s target_process_id=%s",
            request.operation_id,
            request.workflow_id,
            request.target.window_token,
            request.target.process_id,
        )
        receipt = self._dispatcher.dispatch(
            request.operation_id,
            request.target,
            active.cancellation,
        )
        logger.info(
            "Paste trace stage=dispatch_returned operation_id=%s workflow_id=%s "
            "receipt=%s detail_present=%s",
            request.operation_id,
            request.workflow_id,
            receipt.state,
            bool(receipt.detail),
        )
        return receipt

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
            _failed_outcome(error),
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
        with self._lock:
            active.state = "completed"
            if self._active is active:
                self._active = None
        logger.info(
            "Paste trace stage=terminal operation_id=%s workflow_id=%s "
            "state=%s delivery=%s cleanup=%s reason=%s",
            active.request.operation_id,
            active.request.workflow_id,
            outcome.state,
            outcome.delivery,
            outcome.cleanup,
            outcome.reason or "none",
        )
        self._completion_sink(completion)

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
        return PasteOutcome(
            "cleanup_failed",
            delivery,
            "failed",
            message,
            "clipboard_unavailable",
        )
    if result.value is not None:
        message = result.value.detail or "Paste command was sent, but the target application cannot confirm completion. Check the target before trying again."
        if result.cleanup == "external_change":
            message += " The clipboard changed externally, so ClipAI did not overwrite it."
        return PasteOutcome("dispatched_unconfirmed", delivery, result.cleanup, message)
    if result.cancelled or isinstance(result.error, CancelledError):
        return PasteOutcome("cancelled", "not_dispatched", result.cleanup)
    return _failed_outcome(result.error, cleanup=result.cleanup)


def _failed_outcome(
    error: BaseException | None,
    *,
    cleanup: Literal["not_required", "restored", "external_change", "failed"] = "not_required",
) -> PasteOutcome:
    failure = _paste_failure(error)
    return PasteOutcome(
        "failed",
        "not_dispatched",
        cleanup,
        str(failure),
        failure.reason,
    )


def _paste_failure(error: BaseException | None) -> PasteFailure:
    if isinstance(error, PasteFailure):
        return error
    return PasteFailure("unknown", PASTE_FAILURE_MESSAGES["unknown"])
