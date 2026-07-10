from __future__ import annotations

import pytest

from ClipAI.core.errors import ProviderAuthError, ProviderResponseError, ProviderTimeoutError
from ClipAI.core.models import LLMMessage, LLMRequest
from ClipAI.core.state import CancellationToken
from ClipAI.providers.fake import FakeProvider
from ClipAI.providers.gemini import GeminiProvider
from ClipAI.providers.http_transport import HttpResponse
from ClipAI.providers.settings import GeminiSettings


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


def request(model: str = "test-model") -> LLMRequest:
    return LLMRequest((LLMMessage("system", "Be concise"), LLMMessage("user", "Hello")), model, 0.2)


def test_fake_provider_implements_common_contract() -> None:
    result = FakeProvider("ok").complete(request(), CancellationToken())
    assert (result.text, result.provider, result.model) == ("ok", "fake", "test-model")


def test_gemini_maps_payload_and_response(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_KEY", "secret")
    transport = FakeTransport(HttpResponse(200, "", {
        "candidates": [{"content": {"parts": [{"text": "Gemini result"}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 4},
    }))
    provider = GeminiProvider(GeminiSettings("GEMINI_KEY", "https://gemini.test", "gemini", 10), transport)
    result = provider.complete(request("gemini"), CancellationToken())
    assert result.text == "Gemini result"
    assert result.usage and result.usage.output_tokens == 4
    assert transport.calls[0][0].endswith("/v1beta/models/gemini:generateContent")


def test_gemini_missing_key_is_auth_error(monkeypatch) -> None:
    monkeypatch.delenv("MISSING_KEY", raising=False)
    provider = GeminiProvider(GeminiSettings("MISSING_KEY", "https://test", "m", 1), FakeTransport())
    with pytest.raises(ProviderAuthError):
        provider.complete(request(), CancellationToken())


def test_gemini_preserves_transport_timeout(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_KEY", "secret")
    provider = GeminiProvider(
        GeminiSettings("GEMINI_KEY", "https://test", "m", 1),
        FakeTransport(error=ProviderTimeoutError("timed out")),
    )
    with pytest.raises(ProviderTimeoutError):
        provider.complete(request(), CancellationToken())


def test_gemini_invalid_json_is_response_error(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_KEY", "secret")
    provider = GeminiProvider(
        GeminiSettings("GEMINI_KEY", "https://test", "m", 1),
        FakeTransport(HttpResponse(200, "not json", None)),
    )
    with pytest.raises(ProviderResponseError, match="invalid JSON"):
        provider.complete(request(), CancellationToken())

