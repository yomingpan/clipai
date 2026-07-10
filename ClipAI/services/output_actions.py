from __future__ import annotations

from ClipAI.core.ports import ArchiveStore, ClipboardWriter, KeyboardOutput, SpeechOutput


class OutputActions:
    def __init__(
        self,
        *,
        clipboard: ClipboardWriter,
        archive: ArchiveStore | None = None,
        speech: SpeechOutput | None = None,
        keyboard: KeyboardOutput | None = None,
    ) -> None:
        self._clipboard = clipboard
        self._archive = archive
        self._speech = speech
        self._keyboard = keyboard

    def copy(self, text: str) -> None:
        self._clipboard.write_text(text)

    def archive(self, text: str) -> None:
        if self._archive is None:
            raise RuntimeError("archive output is not configured")
        self._archive.save(text)

    @property
    def can_archive(self) -> bool:
        return self._archive is not None

    def paste(self, text: str) -> None:
        if self._keyboard is None:
            raise RuntimeError("keyboard output is not configured")
        self._clipboard.write_text(text)
        self._keyboard.paste()

    @property
    def can_paste(self) -> bool:
        return self._keyboard is not None

    def speak(self, text: str) -> None:
        if self._speech is None:
            raise RuntimeError("speech output is not configured")
        self._speech.speak(text)

    @property
    def can_speak(self) -> bool:
        return self._speech is not None

    def stop_speech(self) -> None:
        if self._speech is not None:
            self._speech.stop()
