from __future__ import annotations

import time
from collections.abc import Callable

from ClipAI.core.ports import ArchiveStore, ClipboardStore, KeyboardOutput, SpeechOutput
from ClipAI.services.speech_text import SpeechTextPreprocessor


class OutputActions:
    def __init__(
        self,
        *,
        clipboard: ClipboardStore,
        archive: ArchiveStore | None = None,
        speech: SpeechOutput | None = None,
        keyboard: KeyboardOutput | None = None,
        paste_restore_delay_sec: float = 0.25,
        wait: Callable[[float], None] = time.sleep,
        speech_text: SpeechTextPreprocessor | None = None,
    ) -> None:
        self._clipboard = clipboard
        self._archive = archive
        self._speech = speech
        self._keyboard = keyboard
        self._paste_restore_delay_sec = paste_restore_delay_sec
        self._wait = wait
        self._speech_text = speech_text or SpeechTextPreprocessor()

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
        original = self._clipboard.read_text()
        try:
            self._clipboard.write_text(text)
            self._keyboard.paste()
            self._wait(self._paste_restore_delay_sec)
        finally:
            self._clipboard.write_text(original)

    @property
    def can_paste(self) -> bool:
        return self._keyboard is not None

    def speak(self, text: str) -> None:
        if self._speech is None:
            raise RuntimeError("speech output is not configured")
        prepared = self._speech_text.prepare(text)
        if prepared:
            self._speech.speak(prepared)

    @property
    def can_speak(self) -> bool:
        return self._speech is not None

    def stop_speech(self) -> None:
        if self._speech is not None:
            self._speech.stop()
