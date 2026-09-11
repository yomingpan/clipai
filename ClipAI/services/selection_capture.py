from __future__ import annotations

import uuid
import logging
import time

from ClipAI.core.ports import SelectionCaptureAdapter, SelectionProbe
from ClipAI.core.models import ExternalWindowRef, SelectionCaptureOutcome, SelectionCaptureRequest
from ClipAI.core.state import CancellationToken
from ClipAI.services.clipboard_transaction import ClipboardTransactionCoordinator


logger = logging.getLogger("clipai.selection")
_MODIFIER_KEYS = ("ctrl", "alt", "shift")


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
            outcome = self._wait_for_modifier_release(cancellation)
            if outcome is not None:
                return outcome
            if not self._probe.source_is_current(source):
                outcome = SelectionCaptureOutcome(reason="source_changed")
                return outcome
            outcome = self._probe.probe(source, cancellation)
            if cancellation is not None and cancellation.is_cancelled:
                outcome = SelectionCaptureOutcome(status="cancelled")
            elif outcome.focus_restored:
                rebased = self._probe.capture_source(source.window)
                if (
                    rebased is None
                    or rebased.window.window_token != source.window.window_token
                    or rebased.window.process_id != source.window.process_id
                ):
                    outcome = SelectionCaptureOutcome(reason="source_changed", strategy="uia")
                else:
                    source = rebased
            if outcome.status != "cancelled" and outcome.reason != "source_changed" and not self._probe.source_is_current(source):
                outcome = SelectionCaptureOutcome(reason="source_changed", strategy="uia")
            elif outcome.status == "unknown" and (
                outcome.selection_detected or outcome.copy_selection_only
            ):
                # An unsupported editor may copy its entire current line.
                # Require positive selection evidence or a verified source whose
                # Copy command cannot substitute unselected document/line text.
                outcome = self._transactions.capture_selection(
                    operation_id, self._adapter, cancellation=cancellation,
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

    def _wait_for_modifier_release(
        self,
        cancellation: CancellationToken | None,
    ) -> SelectionCaptureOutcome | None:
        deadline = time.monotonic() + self._modifier_release_timeout_sec
        while True:
            pressed = tuple(
                self._adapter.modifier_is_pressed(key) is True
                for key in _MODIFIER_KEYS
            )
            if not any(pressed):
                return None
            if cancellation is not None and cancellation.is_cancelled:
                return SelectionCaptureOutcome(status="cancelled")
            if time.monotonic() >= deadline:
                return SelectionCaptureOutcome(reason="modifier_timeout")
            time.sleep(self._poll_sec)
