from __future__ import annotations

import pytest

from ClipAI.core.errors import ConfigError, ProviderAuthError
from ClipAI.core.models import LLMMessage, LLMRequest
from ClipAI.core.state import CancellationToken
from ClipAI.providers.gateway import OpenAICompatibleGatewayProvider, normalize_gateway_base_url
from ClipAI.providers.http_transport import HttpResponse
from ClipAI.providers.settings import GatewaySettings, ProviderCredential
from tests.providers.async_helpers import complete


class FakeTransport:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_gateway_maps_chat_completions_with_optional_key() -> None:
    response = HttpResponse(200, "", {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 1, "completion_tokens": 2}})
    transport = FakeTransport(response)
    settings = GatewaySettings("Local", "http://localhost:8000", "local-model", 10)
    provider = OpenAICompatibleGatewayProvider(settings, ProviderCredential("KEY"), transport)
    result = complete(provider, LLMRequest((LLMMessage("user", "hello"),), "local-model", 0.2))
    assert result.text == "ok"
    assert transport.calls[0][0] == "http://localhost:8000/v1/chat/completions"
    assert "Authorization" not in transport.calls[0][1]["headers"]


def test_gateway_sends_bearer_key_without_exposing_it_in_error() -> None:
    transport = FakeTransport(HttpResponse(401, "echo secret", None))
    settings = GatewaySettings("Remote", "https://gateway.test/v1", "model", 10)
    provider = OpenAICompatibleGatewayProvider(settings, ProviderCredential("KEY", "top-secret"), transport)
    with pytest.raises(ProviderAuthError) as error:
        complete(provider, LLMRequest((LLMMessage("user", "hello"),), "model", 0.2))
    assert transport.calls[0][1]["headers"]["Authorization"] == "Bearer top-secret"
    assert "top-secret" not in str(error.value)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://localhost:11434", "http://localhost:11434/v1"),
        ("https://gateway.test/v1/", "https://gateway.test/v1"),
        ("https://gateway.test/api", "https://gateway.test/api/v1"),
    ],
)
def test_gateway_url_normalization(url: str, expected: str) -> None:
    assert normalize_gateway_base_url(url) == expected


def test_gateway_rejects_remote_http_and_query_credentials() -> None:
    with pytest.raises(ConfigError, match="HTTPS"):
        normalize_gateway_base_url("http://gateway.test")
    with pytest.raises(ConfigError, match="query"):
        normalize_gateway_base_url("https://gateway.test?key=secret")
