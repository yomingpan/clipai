from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest

from ClipAI.core.errors import ProviderResponseError
from ClipAI.core.models import LLMCompleted, LLMMessage, LLMRequest, LLMTextDelta
from ClipAI.core.state import CancellationToken
from ClipAI.providers.anthropic import AnthropicProvider
from ClipAI.providers.gateway import OpenAICompatibleGatewayProvider
from ClipAI.providers.gemini import GeminiProvider
from ClipAI.providers.http_transport import HttpLineResponse
from ClipAI.providers.openai import OpenAIProvider
from ClipAI.providers.settings import AnthropicSettings, GatewaySettings, GeminiSettings, OpenAISettings, ProviderCredential


class StreamingTransport:
    def __init__(self, lines: list[str], status_code: int = 200) -> None:
        self._lines = lines
        self._status_code = status_code
        self.calls = []

    @asynccontextmanager
    async def stream_lines(self, url, **kwargs):
        self.calls.append((url, kwargs))

        async def lines():
            for line in self._lines:
                yield line

        yield HttpLineResponse(self._status_code, lines())


def request(model: str) -> LLMRequest:
    return LLMRequest((LLMMessage("user", "hello"),), model, 0.2)


def collect(provider, model: str):
    async def run():
        return [event async for event in provider.execute(request(model), CancellationToken(), stream=True)]

    return asyncio.run(run())


def assert_stream(events, expected: str) -> None:
    assert "".join(event.text for event in events if isinstance(event, LLMTextDelta)) == expected
    completed = [event for event in events if isinstance(event, LLMCompleted)]
    assert len(completed) == 1
    assert completed[0].result.text == expected


def test_openai_fragmented_sse_preserves_usage_and_terminal_metadata() -> None:
    transport = StreamingTransport([
        'event: response.output_text.delta',
        'data: {"type":"response.output_text.delta","delta":"Hel"}',
        '',
        'data: {"type":"response.output_text.delta","delta":"lo"}',
        'data: {"type":"response.completed","response":{"status":"completed","usage":{"input_tokens":2,"output_tokens":3}}}',
        'data: [DONE]',
    ])
    provider = OpenAIProvider(OpenAISettings("KEY", "https://openai.test", "gpt", 10), ProviderCredential("KEY", "secret"), transport)
    events = collect(provider, "gpt")
    assert_stream(events, "Hello")
    assert events[-1].result.usage.output_tokens == 3


def test_gemini_stream_maps_sse_candidates() -> None:
    transport = StreamingTransport([
        'data: {"candidates":[{"content":{"parts":[{"text":"Gem"}]}}]}',
        'data: {"candidates":[{"content":{"parts":[{"text":"ini"}]},"finishReason":"STOP"}],"usageMetadata":{"promptTokenCount":1,"candidatesTokenCount":2}}',
    ])
    provider = GeminiProvider(GeminiSettings("KEY", "https://gemini.test", "gemini", 10), ProviderCredential("KEY", "secret"), transport)
    assert_stream(collect(provider, "gemini"), "Gemini")


def test_anthropic_stream_maps_content_deltas() -> None:
    transport = StreamingTransport([
        'data: {"type":"message_start","message":{"usage":{"input_tokens":2}}}',
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Clau"}}',
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"de"}}',
        'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":2}}',
    ])
    provider = AnthropicProvider(AnthropicSettings("KEY", "https://anthropic.test", "claude", 10, "2023-06-01", 100), ProviderCredential("KEY", "secret"), transport)
    assert_stream(collect(provider, "claude"), "Claude")


def test_gateway_accepts_non_sse_single_json_fallback() -> None:
    transport = StreamingTransport([
        '{"choices":[{"message":{"content":"local result"},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":2}}',
    ])
    provider = OpenAICompatibleGatewayProvider(GatewaySettings("Local", "http://localhost:8000", "local", 10), ProviderCredential("KEY"), transport)
    assert_stream(collect(provider, "local"), "local result")


def test_malformed_stream_without_text_is_typed_response_error() -> None:
    transport = StreamingTransport(['data: {bad json}', 'data: {"type":"response.completed","response":{"status":"failed"}}'])
    provider = OpenAIProvider(OpenAISettings("KEY", "https://openai.test", "gpt", 10), ProviderCredential("KEY", "secret"), transport)
    with pytest.raises(ProviderResponseError, match="empty response"):
        collect(provider, "gpt")
