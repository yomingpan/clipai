from __future__ import annotations

from ClipAI.core.errors import CancelledError
from ClipAI.core.models import LLMCompleted, LLMRequest, LLMResult, LLMTextDelta, TextContent
from ClipAI.core.state import CancellationToken


class FakeProvider:
    def __init__(self, result: str | None = None) -> None:
        self._result = result

    async def execute(self, request: LLMRequest, cancellation: CancellationToken, *, stream: bool):
        if cancellation.is_cancelled:
            raise CancelledError("request cancelled")
        user_message = request.messages[-1].content if request.messages else ""
        text = self._result or (
            "# Fake Result\n\n"
            "Vertical slice is connected.\n\n"
            f"{_compact_preview(user_message)}"
        )
        if stream:
            yield LLMTextDelta(text)
        yield LLMCompleted(LLMResult(text=text, provider="fake", model=request.model, finish_reason="stop"))


def _compact_preview(text, limit: int = 120) -> str:
    if not isinstance(text, str):
        text = " ".join(part.text for part in text if isinstance(part, TextContent))
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 1]}..."
