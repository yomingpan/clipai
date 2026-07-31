from __future__ import annotations

import asyncio

from ClipAI.core.models import LLMCompleted, LLMRequest, LLMResult
from ClipAI.core.ports import LLMProvider
from ClipAI.core.state import CancellationToken


async def _complete(provider: LLMProvider, request: LLMRequest) -> LLMResult:
    completed: LLMResult | None = None
    async for event in provider.execute(request, CancellationToken(), stream=False):
        if isinstance(event, LLMCompleted):
            completed = event.result
    assert completed is not None
    return completed


def complete(provider: LLMProvider, request: LLMRequest) -> LLMResult:
    return asyncio.run(_complete(provider, request))


def run(awaitable):
    return asyncio.run(awaitable)
