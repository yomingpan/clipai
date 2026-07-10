from __future__ import annotations

from ClipAI.core.ports import ArchiveStore, ClipboardWriter, SpeechOutput


class OutputActions:
    def __init__(
        self,
        *,
        clipboard: ClipboardWriter,
        archive: ArchiveStore | None = None,
        speech: SpeechOutput | None = None,
    ) -> None:
        self._clipboard = clipboard
        self._archive = archive
        self._speech = speech

    def copy(self, text: str) -> None:
        self._clipboard.write_text(text)

    def archive(self, text: str) -> None:
        if self._archive is None:
            raise RuntimeError("archive output is not configured")
        self._archive.save(text)

    def speak(self, text: str) -> None:
        if self._speech is None:
            raise RuntimeError("speech output is not configured")
        self._speech.speak(text)

