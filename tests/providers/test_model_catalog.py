from __future__ import annotations

import pytest

from ClipAI.core.errors import ProviderAuthError, ProviderResponseError
from ClipAI.providers.http_transport import HttpResponse
from ClipAI.providers.model_catalog import ProviderModelCatalogClient
from ClipAI.providers.settings import AnthropicSettings, GatewaySettings, GeminiSettings, OpenAISettings


class FakeTransport:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_openai_catalog_validates_with_bearer_header() -> None:
    transport = FakeTransport(HttpResponse(200, "", {"data": [{"id": "gpt-a"}]}))
    client = ProviderModelCatalogClient(transport)
    models = client.list_models("openai", OpenAISettings("KEY", "https://openai.test", "gpt-a", 10), "secret")
    assert models == ("gpt-a",)
    assert transport.calls[0][0] == "https://openai.test/v1/models"
    assert transport.calls[0][1]["headers"] == {"Authorization": "Bearer secret"}


def test_gemini_catalog_normalizes_model_names() -> None:
    transport = FakeTransport(HttpResponse(200, "", {"models": [{"name": "models/gemini-a"}]}))
    settings = GeminiSettings("KEY", "https://gemini.test", "gemini-a", 10)
    assert ProviderModelCatalogClient(transport).list_models("gemini", settings, "secret") == ("gemini-a",)


def test_anthropic_catalog_sends_version_header() -> None:
    transport = FakeTransport(HttpResponse(200, "", {"data": [{"id": "claude-a"}]}))
    settings = AnthropicSettings("KEY", "https://anthropic.test", "claude-a", 10, "2023-06-01", 100)
    ProviderModelCatalogClient(transport).list_models("anthropic", settings, "secret")
    assert transport.calls[0][1]["headers"]["anthropic-version"] == "2023-06-01"


def test_catalog_rejects_auth_and_invalid_metadata_without_secret() -> None:
    client = ProviderModelCatalogClient(FakeTransport(HttpResponse(401, "secret echoed", None)))
    settings = OpenAISettings("KEY", "https://openai.test", "gpt-a", 10)
    with pytest.raises(ProviderAuthError) as error:
        client.list_models("openai", settings, "top-secret")
    assert "top-secret" not in str(error.value)

    invalid = ProviderModelCatalogClient(FakeTransport(HttpResponse(200, "", {"wrong": []})))
    with pytest.raises(ProviderResponseError, match="invalid model metadata"):
        invalid.list_models("openai", settings, "secret")


def test_gateway_catalog_falls_back_to_explicit_minimal_completion() -> None:
    class GatewayTransport:
        def __init__(self) -> None:
            self.calls = []

        def get(self, url, **kwargs):
            self.calls.append(("get", url, kwargs))
            return HttpResponse(404, "", None)

        def post(self, url, **kwargs):
            self.calls.append(("post", url, kwargs))
            return HttpResponse(200, "", {"choices": [{"message": {"content": "OK"}}]})

    transport = GatewayTransport()
    settings = GatewaySettings("Local", "http://localhost:8000", "model-a", 10)
    models = ProviderModelCatalogClient(transport).list_models("gateway", settings, "")
    assert models == ("model-a",)
    assert [call[0] for call in transport.calls] == ["get", "post"]
