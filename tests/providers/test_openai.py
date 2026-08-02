from __future__ import annotations

import pytest

from ClipAI.core.errors import ProviderAuthError, ProviderResponseError, ProviderTimeoutError
from ClipAI.core.models import LLMMessage, LLMRequest
from ClipAI.core.state import CancellationToken
from ClipAI.providers.http_transport import HttpResponse
from ClipAI.providers.openai import OpenAIProvider
from ClipAI.providers.settings import OpenAISettings, ProviderCredential
from tests.providers.async_helpers import complete


class FakeTransport:
    def __init__(self, response: HttpResponse | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[tuple[str, dict]] = []

    async def post(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        assert self.response is not None
        return self.response


def request() -> LLMRequest:
    return LLMRequest((LLMMessage("system", "Be concise"), LLMMessage("user", "Hello")), "gpt", 0.2)


def test_openai_maps_responses_api() -> None:
    payload = {
        "status": "completed",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": "OpenAI result"}]}],
        "usage": {"input_tokens": 2, "output_tokens": 5},
    }
    transport = FakeTransport(HttpResponse(200, "", payload))
    provider = OpenAIProvider(OpenAISettings("OPENAI_KEY", "https://openai.test", "gpt", 10), ProviderCredential("OPENAI_KEY", "secret"), transport)
    result = complete(provider, request())
    assert result.text == "OpenAI result"
    assert result.usage and result.usage.output_tokens == 5
    assert transport.calls[0][0] == "https://openai.test/v1/responses"
    assert transport.calls[0][1]["json"]["instructions"] == "Be concise"


def test_openai_missing_key_is_auth_error() -> None:
    provider = OpenAIProvider(OpenAISettings("OPENAI_MISSING", "https://test", "gpt", 1), ProviderCredential("OPENAI_MISSING"), FakeTransport())
    with pytest.raises(ProviderAuthError):
        complete(provider, request())


def test_openai_preserves_timeout_error() -> None:
    provider = OpenAIProvider(
        OpenAISettings("OPENAI_KEY", "https://test", "gpt", 1),
        ProviderCredential("OPENAI_KEY", "secret"), FakeTransport(error=ProviderTimeoutError("timed out")),
    )
    with pytest.raises(ProviderTimeoutError):
        complete(provider, request())


def test_openai_invalid_json_is_response_error() -> None:
    provider = OpenAIProvider(
        OpenAISettings("OPENAI_KEY", "https://test", "gpt", 1),
        ProviderCredential("OPENAI_KEY", "secret"), FakeTransport(HttpResponse(200, "invalid", None)),
    )
    with pytest.raises(ProviderResponseError, match="invalid JSON"):
        complete(provider, request())
