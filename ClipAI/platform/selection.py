from __future__ import annotations


class NoopSelectionReader:
    """Safe fallback until an OS-specific selection reader is configured."""

    def read_text(self) -> str:
        return ""

