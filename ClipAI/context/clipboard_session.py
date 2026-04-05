from __future__ import annotations

from contextlib import AbstractContextManager
import threading
import time

from clipai.platform.clipboard import capture_clipboard_snapshot, restore_clipboard_snapshot


class ClipboardSession(AbstractContextManager["ClipboardSession"]):
    """Temporarily borrows the clipboard and restores it on exit."""

    def __init__(self) -> None:
        self._snapshot: dict | None = None
        self._restored = False

    def __enter__(self) -> "ClipboardSession":
        self._snapshot = capture_clipboard_snapshot()
        self._restored = False
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb
        self.restore()
        return None

    def restore(self) -> None:
        if self._restored:
            return
        if self._snapshot is not None:
            restore_clipboard_snapshot(self._snapshot)
        self._restored = True

    def restore_later(self, delay_sec: float) -> threading.Thread:
        def _worker() -> None:
            time.sleep(max(0.0, delay_sec))
            self.restore()

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        return thread
