from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
import threading
import uuid

from ClipAI.core.models import SpeechRequest
from ClipAI.core.ports import ClipboardReader, OperationHandle, OperationTracker, SelectionReader, SpeechOutput
from ClipAI.core.state import CancellationToken
from ClipAI.services.speech_text import SpeechTextPreprocessor


class SpeechVoiceSelector:
    def __init__(self, english_voice: str) -> None:
        self._english_voice = english_voice

    def select(self, text: str) -> str | None:
        if any("\u4e00" <= char <= "\u9fff" for char in text):
            return None
        return self._english_voice


@dataclass(frozen=True)
class SpeechJob:
    operation_id: str
    run: Callable[[], None]


class SpeechCoordinator:
    def __init__(
        self,
        *,
        clipboard: ClipboardReader,
        selection_reader: SelectionReader,
        speech: SpeechOutput,
        voice_selector: SpeechVoiceSelector,
        operation_tracker: OperationTracker | None = None,
        speech_text: SpeechTextPreprocessor | None = None,
    ) -> None:
        self._clipboard = clipboard
        self._selection_reader = selection_reader
        self._speech = speech
        self._voice_selector = voice_selector
        self._operation_tracker = operation_tracker
        self._speech_text = speech_text or SpeechTextPreprocessor()
        self._lock = threading.RLock()
        self._current: tuple[CancellationToken, OperationHandle | None] | None = None

    def create_job(self, *, clipboard_only: bool) -> SpeechJob:
        self.cancel_current()
        source = "clipboard" if clipboard_only else "selection"
        operation_id = f"tts:{source}:{uuid.uuid4().hex}"
        token = CancellationToken()
        operation = self._operation_tracker.start(operation_id, "tts") if self._operation_tracker else None
        with self._lock:
            self._current = (token, operation)

        def run() -> None:
            try:
                if token.is_cancelled:
                    return
                text = self._read_text(clipboard_only=clipboard_only)
                prepared = self._speech_text.prepare(text)
                if prepared and not token.is_cancelled:
                    request = SpeechRequest(prepared, self._voice_selector.select(prepared), token)
                    self._speech.speak(request)
                if operation is not None:
                    if not token.is_cancelled:
                        operation.succeed()
            except BaseException:
                if operation is not None:
                    if not token.is_cancelled:
                        operation.fail()
                raise
            finally:
                with self._lock:
                    if self._current is not None and self._current[0] is token:
                        self._current = None

        return SpeechJob(operation_id, run)

    def cancel_current(self) -> None:
        with self._lock:
            current = self._current
            self._current = None
        if current is not None:
            token, operation = current
            token.cancel()
            if operation is not None:
                operation.cancel()
        self._speech.stop()

    def _read_text(self, *, clipboard_only: bool) -> str:
        if not clipboard_only:
            selected = self._selection_reader.read_text().strip()
            if selected:
                return selected
        return self._clipboard.read_text()
