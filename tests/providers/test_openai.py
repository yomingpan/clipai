from __future__ import annotations

import pytest

from ClipAI.core.errors import ProviderAuthError, ProviderResponseError, ProviderTimeoutError
from ClipAI.core.models import LLMMessage, LLMRequest
from ClipAI.core.state import CancellationToken
from ClipAI.providers.http_transport import HttpResponse
from ClipAI.providers.openai import OpenAIProvider
from ClipAI.providers.settings import OpenAISettings


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


def request() -> LLMRequest:
    return LLMRequest((LLMMessage("system", "Be concise"), LLMMessage("user", "Hello")), "gpt", 0.2)


def test_openai_maps_responses_api(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_KEY", "secret")
    payload = {
        "status": "completed",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": "OpenAI result"}]}],
        "usage": {"input_tokens": 2, "output_tokens": 5},
    }
    transport = FakeTransport(HttpResponse(200, "", payload))
    provider = OpenAIProvider(OpenAISettings("OPENAI_KEY", "https://openai.test", "gpt", 10), transport)
    result = provider.complete(request(), CancellationToken())
    assert result.text == "OpenAI result"
    assert result.usage and result.usage.output_tokens == 5
    assert transport.calls[0][0] == "https://openai.test/v1/responses"
    assert transport.calls[0][1]["json"]["instructions"] == "Be concise"


def test_openai_missing_key_is_auth_error(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_MISSING", raising=False)
    provider = OpenAIProvider(OpenAISettings("OPENAI_MISSING", "https://test", "gpt", 1), FakeTransport())
    with pytest.raises(ProviderAuthError):
        provider.complete(request(), CancellationToken())


def test_openai_preserves_timeout_error(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_KEY", "secret")
    provider = OpenAIProvider(
        OpenAISettings("OPENAI_KEY", "https://test", "gpt", 1),
        FakeTransport(error=ProviderTimeoutError("timed out")),
    )
    with pytest.raises(ProviderTimeoutError):
        provider.complete(request(), CancellationToken())


def test_openai_invalid_json_is_response_error(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_KEY", "secret")
    provider = OpenAIProvider(
        OpenAISettings("OPENAI_KEY", "https://test", "gpt", 1),
        FakeTransport(HttpResponse(200, "invalid", None)),
    )
    with pytest.raises(ProviderResponseError, match="invalid JSON"):
        provider.complete(request(), CancellationToken())

