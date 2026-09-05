from __future__ import annotations

import uuid
import logging
import time

from ClipAI.core.ports import SelectionCaptureAdapter, SelectionProbe
from ClipAI.core.models import ExternalWindowRef, SelectionCaptureOutcome, SelectionCaptureRequest
from ClipAI.core.state import CancellationToken
from ClipAI.services.clipboard_transaction import ClipboardTransactionCoordinator


logger = logging.getLogger("clipai.selection")


class SelectionCaptureCoordinator:
    def __init__(
        self,
        clipboard_transactions: ClipboardTransactionCoordinator,
        adapter: SelectionCaptureAdapter,
        probe: SelectionProbe,
        *,
        modifier_release_timeout_sec: float = 1.0,
        timeout_sec: float = 0.35,
        poll_sec: float = 0.02,
    ) -> None:
        self._transactions = clipboard_transactions
        self._adapter = adapter
        self._probe = probe
        self._modifier_release_timeout_sec = modifier_release_timeout_sec
        self._timeout_sec = timeout_sec
        self._poll_sec = poll_sec

    def begin_capture(self, target: ExternalWindowRef | None = None) -> SelectionCaptureRequest:
        try:
            source = self._probe.capture_source(target)
        except Exception:
            source = None
        return SelectionCaptureRequest(f"selection:{uuid.uuid4().hex}", source)

    def capture(
        self, cancellation: CancellationToken | None = None, *,
        target: ExternalWindowRef | None = None,
        request: SelectionCaptureRequest | None = None,
    ) -> SelectionCaptureOutcome:
        bound = request or self.begin_capture(target)
        operation_id = bound.operation_id
        started = time.monotonic()
        source = None
        outcome = SelectionCaptureOutcome(reason="source_unavailable")
        try:
            if cancellation is not None and cancellation.is_cancelled:
                outcome = SelectionCaptureOutcome(status="cancelled")
                return outcome
            source = bound.source
            if source is None:
                return outcome
            if not self._probe.source_is_current(source):
                outcome = SelectionCaptureOutcome(reason="source_changed")
                return outcome
            outcome = self._probe.probe(source, cancellation)
            if cancellation is not None and cancellation.is_cancelled:
                outcome = SelectionCaptureOutcome(status="cancelled")
            elif not self._probe.source_is_current(source):
                outcome = SelectionCaptureOutcome(reason="source_changed", strategy="uia")
            elif outcome.status == "unknown" and outcome.selection_detected:
                # An unsupported editor may copy its entire current line.
                # Require positive selection evidence before synthetic copy.
                outcome = self._transactions.capture_selection(
                    operation_id, self._adapter, cancellation=cancellation,
                    modifier_release_timeout_sec=self._modifier_release_timeout_sec,
                    timeout_sec=self._timeout_sec, poll_sec=self._poll_sec,
                    source_is_current=lambda: self._probe.source_is_current(source),
                )
            return outcome
        except Exception:
            outcome = SelectionCaptureOutcome(reason="capture_failed")
            return outcome
        finally:
            logger.info(
                "Selection capture operation_id=%s target=%s status=%s reason=%s "
                "strategy=%s elapsed_ms=%d", operation_id,
                source.window.window_token if source is not None else "unavailable",
                outcome.status, outcome.reason, outcome.strategy,
                int((time.monotonic() - started) * 1000),
            )
