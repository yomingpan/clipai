from __future__ import annotations

from contextlib import contextmanager
import threading
from collections.abc import Iterator

from ClipAI.core.ports import ClipboardTransactionStore


class ClipboardTransactionCoordinator:
    """Serialize temporary clipboard ownership and restore only owned content."""

    def __init__(self, clipboard: ClipboardTransactionStore) -> None:
        self._clipboard = clipboard
        self._lock = threading.Lock()

    @contextmanager
    def temporary_text(self, text: str) -> Iterator[None]:
        with self._lock:
            original = self._clipboard.snapshot()
            self._clipboard.write_text(text)
            owned_sequence = self._clipboard.sequence_number()
            try:
                yield
            finally:
                self._clipboard.restore_if_unchanged(original, owned_sequence)
