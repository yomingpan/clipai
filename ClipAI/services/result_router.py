from __future__ import annotations

from collections.abc import Callable

from ClipAI.core.models import ProcessedResult, ResultRoute


class ResultRouter:
    def __init__(self, speech_sink: Callable[[str], None] | None = None) -> None:
        self._speech_sink = speech_sink

    def route(
        self,
        route: ResultRoute,
        result: ProcessedResult,
        *,
        popup_sink: Callable[[ProcessedResult], None],
    ) -> None:
        if route == "popup":
            popup_sink(result)
            return
        if self._speech_sink is None:
            raise RuntimeError("speech result route is not configured")
        self._speech_sink(result.text)
