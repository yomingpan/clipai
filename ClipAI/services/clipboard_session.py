from __future__ import annotations

from contextlib import AbstractContextManager

from clipai.clipboard import capture_clipboard_snapshot, restore_clipboard_snapshot


class ClipboardSession(AbstractContextManager["ClipboardSession"]):
    """Temporarily borrows the clipboard and restores it on exit."""

    def __init__(self) -> None:
        self._snapshot: dict | None = None

    def __enter__(self) -> "ClipboardSession":
        self._snapshot = capture_clipboard_snapshot()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb
        if self._snapshot is not None:
            restore_clipboard_snapshot(self._snapshot)
        return None
