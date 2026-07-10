from __future__ import annotations

import pytest

from ClipAI.core.errors import ProviderAuthError, ProviderResponseError, ProviderTimeoutError
from ClipAI.core.models import LLMMessage, LLMRequest
from ClipAI.core.state import CancellationToken
from ClipAI.providers.anthropic import AnthropicProvider
from ClipAI.providers.http_transport import HttpResponse
from ClipAI.providers.settings import AnthropicSettings


class FakeTransport:
    def __init__(self, response: HttpResponse | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[tuple[str, dict]] = []

    def post(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        assert self.response is not None
        return self.response


def settings(env: str = "ANTHROPIC_KEY") -> AnthropicSettings:
    return AnthropicSettings(env, "https://anthropic.test", "claude", 10, "2023-06-01", 512)


def request() -> LLMRequest:
    return LLMRequest((LLMMessage("system", "Be concise"), LLMMessage("user", "Hello")), "claude", 0.2)


def test_anthropic_maps_messages_api(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_KEY", "secret")
    payload = {
        "content": [{"type": "text", "text": "Claude result"}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 2, "output_tokens": 6},
    }
    transport = FakeTransport(HttpResponse(200, "", payload))
    result = AnthropicProvider(settings(), transport).complete(request(), CancellationToken())
    assert result.text == "Claude result"
    assert result.usage and result.usage.output_tokens == 6
    assert transport.calls[0][0] == "https://anthropic.test/v1/messages"
    assert transport.calls[0][1]["headers"]["anthropic-version"] == "2023-06-01"
    assert transport.calls[0][1]["json"]["max_tokens"] == 512


def test_anthropic_missing_key_is_auth_error(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_MISSING", raising=False)
    with pytest.raises(ProviderAuthError):
        AnthropicProvider(settings("ANTHROPIC_MISSING"), FakeTransport()).complete(request(), CancellationToken())


def test_anthropic_preserves_timeout_error(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_KEY", "secret")
    provider = AnthropicProvider(settings(), FakeTransport(error=ProviderTimeoutError("timed out")))
    with pytest.raises(ProviderTimeoutError):
        provider.complete(request(), CancellationToken())


def test_anthropic_invalid_json_is_response_error(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_KEY", "secret")
    provider = AnthropicProvider(settings(), FakeTransport(HttpResponse(200, "invalid", None)))
    with pytest.raises(ProviderResponseError, match="invalid JSON"):
        provider.complete(request(), CancellationToken())

