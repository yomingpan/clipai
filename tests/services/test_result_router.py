import asyncio

import pytest

from ClipAI.core.models import ProcessedResult
from ClipAI.services.result_router import ResultRouter


def test_popup_route_uses_popup_sink() -> None:
    results = []
    asyncio.run(ResultRouter().route("popup", ProcessedResult("text"), popup_sink=results.append))
    assert results[0].text == "text"


def test_speech_route_uses_injected_sink_without_popup() -> None:
    spoken = []
    popup = []
    class Sink:
        async def speak_result(self, text: str, workflow_id: str, cancellation) -> None:
            del workflow_id, cancellation
            spoken.append(text)
    asyncio.run(ResultRouter(Sink()).route("speech", ProcessedResult("text"), popup_sink=popup.append))
    assert spoken == ["text"]
    assert popup == []


def test_unconfigured_speech_route_fails_explicitly() -> None:
    with pytest.raises(RuntimeError, match="speech result route"):
        asyncio.run(ResultRouter().route("speech", ProcessedResult("text"), popup_sink=lambda _result: None))
