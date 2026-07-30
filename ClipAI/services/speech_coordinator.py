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
    _JAPANESE_RANGES = (
        ("\u3040", "\u309f"),  # Hiragana
        ("\u30a0", "\u30ff"),  # Katakana
        ("\u31f0", "\u31ff"),  # Katakana phonetic extensions
        ("\uff66", "\uff9d"),  # Half-width Katakana
    )

    def __init__(self, english_voice: str, *, japanese_voice: str = "ja-JP-NanamiNeural") -> None:
        self._english_voice = english_voice
        self._japanese_voice = japanese_voice

    def select(self, text: str) -> str | None:
        if any(start <= char <= end for char in text for start, end in self._JAPANESE_RANGES):
            return self._japanese_voice
        if any("\u4e00" <= char <= "\u9fff" for char in text):
            return None
        return self._english_voice


@dataclass(frozen=True)
class SpeechJob:
    operation_id: str
    workflow_id: str
    text: str
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
        self._current: tuple[str, str, CancellationToken, OperationHandle | None] | None = None

    def create_job(self, *, clipboard_only: bool) -> SpeechJob:
        source = "clipboard" if clipboard_only else "selection"
        operation_id = f"tts:{source}:{uuid.uuid4().hex}"
        text = self._read_text(clipboard_only=clipboard_only)
        return self._create_job(
            operation_id=operation_id,
            workflow_id="global",
            text=text,
            track=False,
        )

    def create_text_job(self, *, operation_id: str, workflow_id: str, text: str) -> SpeechJob:
        return self._create_job(operation_id=operation_id, workflow_id=workflow_id, text=text, track=False)

    def speak_result(self, text: str, workflow_id: str, cancellation: CancellationToken) -> None:
        operation_id = f"tts:sequence:{uuid.uuid4().hex}"
        self._create_job(
            operation_id=operation_id,
            workflow_id=workflow_id,
            text=text,
            track=True,
            token=cancellation,
        ).run()

    def _create_job(
        self,
        *,
        operation_id: str,
        workflow_id: str,
        text: str,
        track: bool,
        token: CancellationToken | None = None,
    ) -> SpeechJob:
        self.cancel_current()
        token = token or CancellationToken()
        operation = self._operation_tracker.start(operation_id, "tts") if track and self._operation_tracker else None
        with self._lock:
            self._current = (operation_id, workflow_id, token, operation)

        def run() -> None:
            try:
                if token.is_cancelled:
                    return
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
                    if self._current is not None and self._current[2] is token:
                        self._current = None

        return SpeechJob(operation_id, workflow_id, text, run)

    def is_active_for(self, workflow_id: str) -> bool:
        with self._lock:
            return self._current is not None and self._current[1] == workflow_id

    def operation_for(self, workflow_id: str) -> str | None:
        with self._lock:
            return self._current[0] if self._current is not None and self._current[1] == workflow_id else None

    @property
    def current_identity(self) -> tuple[str, str] | None:
        with self._lock:
            return (self._current[0], self._current[1]) if self._current is not None else None

    def cancel_operation(self, operation_id: str) -> bool:
        with self._lock:
            if self._current is None or self._current[0] != operation_id:
                return False
            current = self._current
            self._current = None
        self._cancel_owned(current)
        return True

    def cancel_workflow(self, workflow_id: str) -> bool:
        with self._lock:
            if self._current is None or self._current[1] != workflow_id:
                return False
            current = self._current
            self._current = None
        self._cancel_owned(current)
        return True

    def cancel_current(self) -> None:
        with self._lock:
            current = self._current
            self._current = None
        if current is not None:
            self._cancel_owned(current)

    def _cancel_owned(self, current: tuple[str, str, CancellationToken, OperationHandle | None]) -> None:
        _operation_id, _workflow_id, token, operation = current
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
