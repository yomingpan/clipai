from __future__ import annotations

import asyncio

from ClipAI.core.models import LLMCompleted, LLMResult, LLMTextDelta
from ClipAI.services.execute_action import coalesce_provider_events


def test_fast_deltas_are_coalesced_and_terminal_event_flushes_immediately() -> None:
    async def source():
        yield LLMTextDelta("a")
        yield LLMTextDelta("b")
        yield LLMTextDelta("c")
        yield LLMCompleted(LLMResult("abc", "fake", "model"))

    async def collect():
        return [event async for event in coalesce_provider_events(source(), interval_seconds=1)]

    events = asyncio.run(collect())
    assert events == [
        LLMTextDelta("abc"),
        LLMCompleted(LLMResult("abc", "fake", "model")),
    ]


def test_slow_delta_is_flushed_within_interval_without_cancelling_source() -> None:
    async def source():
        yield LLMTextDelta("first")
        await asyncio.sleep(0.03)
        yield LLMTextDelta("second")
        yield LLMCompleted(LLMResult("firstsecond", "fake", "model"))

    async def collect():
        return [event async for event in coalesce_provider_events(source(), interval_seconds=0.01)]

    events = asyncio.run(collect())
    assert events == [
        LLMTextDelta("first"),
        LLMTextDelta("second"),
        LLMCompleted(LLMResult("firstsecond", "fake", "model")),
    ]
