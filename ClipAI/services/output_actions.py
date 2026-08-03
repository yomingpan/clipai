from __future__ import annotations

from ClipAI.core.ports import ArchiveStore, ClipboardWriter


class OutputActions:
    def __init__(
        self,
        *,
        clipboard: ClipboardWriter,
        archive: ArchiveStore | None = None,
    ) -> None:
        self._clipboard = clipboard
        self._archive = archive

    def copy(self, text: str) -> None:
        self._clipboard.write_text(text)

    def archive(self, text: str) -> None:
        if self._archive is None:
            raise RuntimeError("archive output is not configured")
        self._archive.save(text)

    @property
    def can_archive(self) -> bool:
        return self._archive is not None
