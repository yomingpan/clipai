from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ClipAI.core.models import ForegroundTarget, ProcessedResult, ResultRoute
from ClipAI.core.state import CancellationToken


class SpeechResultSink(Protocol):
    def speak_result(self, text: str, workflow_id: str, cancellation: CancellationToken) -> None: ...


class WriteResultSink(Protocol):
    def write_result(self, text: str, target: ForegroundTarget | None, workflow_id: str, cancellation: CancellationToken) -> None: ...


class ResultRouter:
    def __init__(self, speech_sink: SpeechResultSink | None = None, write_sink: WriteResultSink | None = None) -> None:
        self._speech_sink = speech_sink
        self._write_sink = write_sink

    def route(
        self,
        route: ResultRoute,
        result: ProcessedResult,
        *,
        popup_sink: Callable[[ProcessedResult], None],
        workflow_id: str = "sequence",
        cancellation: CancellationToken | None = None,
        write_target: ForegroundTarget | None = None,
    ) -> None:
        if route == "popup":
            popup_sink(result)
            return
        if self._speech_sink is None:
            if route == "speech":
                raise RuntimeError("speech result route is not configured")
        if route == "speech":
            self._speech_sink.speak_result(result.text, workflow_id, cancellation or CancellationToken())
            return
        if self._write_sink is None:
            raise RuntimeError("write result route is not configured")
        self._write_sink.write_result(result.text, write_target, workflow_id, cancellation or CancellationToken())
