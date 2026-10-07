from __future__ import annotations

import pytest

from ClipAI.core.errors import ProviderAuthError, ProviderResponseError
from ClipAI.providers.http_transport import HttpResponse
from ClipAI.providers.model_catalog import ProviderModelCatalogClient
from ClipAI.providers.settings import AnthropicSettings, GatewaySettings, GeminiSettings, OpenAISettings
from tests.providers.async_helpers import run


class FakeTransport:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response
        self.calls = []

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_gemini_permission_denial_is_not_reported_as_invalid_key():
    payload = {"error": {"status": "PERMISSION_DENIED", "message": "secret echoed",
                         "details": [{"reason": "API_KEY_SERVICE_BLOCKED"}]}}
    settings = GeminiSettings("KEY", "https://gemini.test", "gemini-a", 10)
    client = ProviderModelCatalogClient(FakeTransport(HttpResponse(403, "secret echoed", payload)))
    with pytest.raises(ProviderResponseError, match="API_KEY_SERVICE_BLOCKED") as raised:
        run(client.list_models("gemini", settings, "secret"))
    assert "secret" not in str(raised.value)


def test_gemini_unknown_permission_denial_does_not_echo_response_or_untrusted_reason():
    settings = GeminiSettings("KEY", "https://gemini.test", "gemini-a", 10)
    client = ProviderModelCatalogClient(FakeTransport(HttpResponse(403, "secret echoed", {
        "error": {"details": [{"reason": "secret echoed"}]}})))
    with pytest.raises(ProviderResponseError, match="HTTP 403") as raised:
        run(client.list_models("gemini", settings, "secret"))
    assert "secret" not in str(raised.value)


@pytest.mark.parametrize("reason", ["API_KEY_INVALID", "API_KEY_EXPIRED"])
def test_gemini_invalid_key_on_http_400_remains_authentication_failure(reason):
    client = ProviderModelCatalogClient(FakeTransport(HttpResponse(400, "secret echoed", {
        "error": {"details": [{"reason": reason}]}})))
    with pytest.raises(ProviderAuthError):
        run(client.list_models("gemini", GeminiSettings("KEY", "https://gemini.test", "gemini-a", 10), "secret"))


def test_gemini_generation_shares_permission_classification():
    from ClipAI.providers.gemini import _raise_for_status
    with pytest.raises(ProviderResponseError, match="API_KEY_SERVICE_BLOCKED"):
        _raise_for_status("Gemini", HttpResponse(403, "secret echoed", {
            "error": {"details": [{"reason": "API_KEY_SERVICE_BLOCKED"}]}}))


def test_gemini_leaked_key_denial_guides_replacement_without_echoing_server_text():
    message = "Your API key was reported as leaked. Please use another API key. secret echoed"
    response = HttpResponse(403, message, {
        "error": {"status": "PERMISSION_DENIED", "message": message}})
    settings = GeminiSettings("KEY", "https://gemini.test", "gemini-a", 10)
    client = ProviderModelCatalogClient(FakeTransport(response))
    with pytest.raises(ProviderResponseError, match="blocked this key as leaked") as raised:
        run(client.list_models("gemini", settings, "secret"))
    assert "Google AI Studio" in str(raised.value)
    assert "secret" not in str(raised.value)


def test_openai_catalog_validates_with_bearer_header() -> None:
    transport = FakeTransport(HttpResponse(200, "", {"data": [{"id": "gpt-a"}]}))
    client = ProviderModelCatalogClient(transport)
    models = run(client.list_models("openai", OpenAISettings("KEY", "https://openai.test", "gpt-a", 10), "secret"))
    assert models == ("gpt-a",)
    assert transport.calls[0][0] == "https://openai.test/v1/models"
    assert transport.calls[0][1]["headers"] == {"Authorization": "Bearer secret"}


def test_gemini_catalog_normalizes_model_names() -> None:
    transport = FakeTransport(HttpResponse(200, "", {"models": [{"name": "models/gemini-a"}]}))
    settings = GeminiSettings("KEY", "https://gemini.test", "gemini-a", 10)
    assert run(ProviderModelCatalogClient(transport).list_models("gemini", settings, "secret")) == ("gemini-a",)
    assert transport.calls[0][1]["headers"] == {"x-goog-api-key": "secret"}
    assert "key" not in transport.calls[0][1].get("params", {})


def test_anthropic_catalog_sends_version_header() -> None:
    transport = FakeTransport(HttpResponse(200, "", {"data": [{"id": "claude-a"}]}))
    settings = AnthropicSettings("KEY", "https://anthropic.test", "claude-a", 10, "2023-06-01", 100)
    run(ProviderModelCatalogClient(transport).list_models("anthropic", settings, "secret"))
    assert transport.calls[0][1]["headers"]["anthropic-version"] == "2023-06-01"


def test_catalog_rejects_auth_and_invalid_metadata_without_secret() -> None:
    client = ProviderModelCatalogClient(FakeTransport(HttpResponse(401, "secret echoed", None)))
    settings = OpenAISettings("KEY", "https://openai.test", "gpt-a", 10)
    with pytest.raises(ProviderAuthError) as error:
        run(client.list_models("openai", settings, "top-secret"))
    assert "top-secret" not in str(error.value)

    invalid = ProviderModelCatalogClient(FakeTransport(HttpResponse(200, "", {"wrong": []})))
    with pytest.raises(ProviderResponseError, match="invalid model metadata"):
        run(invalid.list_models("openai", settings, "secret"))


def test_gateway_catalog_falls_back_to_explicit_minimal_completion() -> None:
    class GatewayTransport:
        def __init__(self) -> None:
            self.calls = []

        async def get(self, url, **kwargs):
            self.calls.append(("get", url, kwargs))
            return HttpResponse(404, "", None)

        async def post(self, url, **kwargs):
            self.calls.append(("post", url, kwargs))
            return HttpResponse(200, "", {"choices": [{"message": {"content": "OK"}}]})

    transport = GatewayTransport()
    settings = GatewaySettings("Local", "http://localhost:8000", "model-a", 10)
    models = run(ProviderModelCatalogClient(transport).list_models("gateway", settings, ""))
    assert models == ("model-a",)
    assert [call[0] for call in transport.calls] == ["get", "post"]


def test_gateway_catalog_requires_fallback_model_when_models_endpoint_is_unavailable() -> None:
    transport = FakeTransport(HttpResponse(404, "", None))
    settings = GatewaySettings("Local", "http://localhost:8000", "", 10)
    with pytest.raises(ProviderResponseError, match="Enter a model ID"):
        run(ProviderModelCatalogClient(transport).list_models("gateway", settings, ""))
    assert len(transport.calls) == 1


def test_gemini_catalog_paginates_filters_and_deduplicates() -> None:
    class PagedTransport:
        def __init__(self) -> None:
            self.calls = []

        async def get(self, url, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return HttpResponse(200, "", {
                    "models": [
                        {"name": "models/gemini-a", "supportedGenerationMethods": ["generateContent"]},
                        {"name": "models/embed", "supportedGenerationMethods": ["embedContent"]},
                    ],
                    "nextPageToken": "next",
                })
            return HttpResponse(200, "", {"models": [{"name": "models/gemini-a"}, {"name": "models/gemini-b"}]})

    transport = PagedTransport()
    settings = GeminiSettings("KEY", "https://gemini.test", "gemini-a", 10)
    models = run(ProviderModelCatalogClient(transport).list_models("gemini", settings, "secret"))
    assert models == ("gemini-a", "gemini-b")
    assert transport.calls[1]["params"]["pageToken"] == "next"
