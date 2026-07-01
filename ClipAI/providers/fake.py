from __future__ import annotations

from ClipAI.core.provider import ProviderRequest


class FakeProvider:
    def complete(self, request: ProviderRequest) -> str:
        user_message = request.messages[-1]["content"] if request.messages else ""
        preview = _compact_preview(user_message)
        return (
            "# Phase 3 Fake Result\n\n"
            "## Core\n"
            "Vertical slice is connected.\n\n"
            "## Input Preview\n"
            f"{preview}\n\n"
            "Synonym: working path, first slice, product skeleton"
        )


def _compact_preview(text: str, limit: int = 120) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 1]}..."
