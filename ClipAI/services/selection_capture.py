from __future__ import annotations

import uuid

from ClipAI.core.ports import SelectionCaptureAdapter
from ClipAI.core.state import CancellationToken
from ClipAI.services.clipboard_transaction import ClipboardTransactionCoordinator


class SelectionCaptureCoordinator:
    def __init__(
        self,
        clipboard_transactions: ClipboardTransactionCoordinator,
        adapter: SelectionCaptureAdapter,
        *,
        modifier_release_timeout_sec: float = 1.0,
        timeout_sec: float = 0.35,
        poll_sec: float = 0.02,
    ) -> None:
        self._transactions = clipboard_transactions
        self._adapter = adapter
        self._modifier_release_timeout_sec = modifier_release_timeout_sec
        self._timeout_sec = timeout_sec
        self._poll_sec = poll_sec

    def read_text(self, cancellation: CancellationToken | None = None) -> str:
        outcome = self._transactions.capture_selection(
            f"selection:{uuid.uuid4().hex}",
            self._adapter,
            cancellation=cancellation,
            modifier_release_timeout_sec=self._modifier_release_timeout_sec,
            timeout_sec=self._timeout_sec,
            poll_sec=self._poll_sec,
        )
        return outcome.text
