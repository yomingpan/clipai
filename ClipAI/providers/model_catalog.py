from __future__ import annotations

from typing import Any

from ClipAI.core.errors import ProviderAuthError, ProviderResponseError
from ClipAI.providers.http_transport import HttpResponse, HttpTransport
from ClipAI.providers.gateway import OpenAICompatibleGatewayProvider, gateway_headers, normalize_gateway_base_url
from ClipAI.providers.settings import AnthropicSettings, GatewaySettings, GeminiSettings, OpenAISettings, ProviderCredential, ProviderSettings


class ProviderModelCatalogClient:
    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    async def list_models(self, provider_id: str, settings: ProviderSettings, api_key: str) -> tuple[str, ...]:
        if provider_id != "gateway" and not api_key.strip():
            raise ProviderAuthError("API key is required")
        if provider_id == "gateway" and isinstance(settings, GatewaySettings):
            response = await self._transport.get(
                f"{normalize_gateway_base_url(settings.base_url)}/models",
                headers=gateway_headers(api_key),
                timeout=settings.timeout_sec,
            )
            if response.status_code in {404, 405}:
                return await self._test_gateway_completion(settings, api_key)
            self._raise_for_status("Gateway", response)
            return _data_models(response.payload)
        if provider_id == "gemini" and isinstance(settings, GeminiSettings):
            return await self._list_gemini(settings, api_key)
        if provider_id == "openai" and isinstance(settings, OpenAISettings):
            response = await self._transport.get(
                f"{settings.base_url.rstrip('/')}/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=settings.timeout_sec,
            )
            self._raise_for_status("OpenAI", response)
            return _data_models(response.payload)
        if provider_id == "anthropic" and isinstance(settings, AnthropicSettings):
            response = await self._transport.get(
                f"{settings.base_url.rstrip('/')}/v1/models",
                headers={"x-api-key": api_key, "anthropic-version": settings.api_version},
                timeout=settings.timeout_sec,
            )
            self._raise_for_status("Anthropic", response)
            return _data_models(response.payload)
        raise ProviderResponseError("Unsupported provider configuration")

    async def _list_gemini(self, settings: GeminiSettings, api_key: str) -> tuple[str, ...]:
        models: list[str] = []
        page_token = ""
        for _page in range(100):
            params = {"key": api_key}
            if page_token:
                params["pageToken"] = page_token
            response = await self._transport.get(
                f"{settings.base_url.rstrip('/')}/v1beta/models",
                params=params,
                timeout=settings.timeout_sec,
            )
            self._raise_for_status("Gemini", response)
            models.extend(_gemini_models(response.payload))
            page_token = str(response.payload.get("nextPageToken") or "")
            if not page_token:
                return tuple(dict.fromkeys(models))
        raise ProviderResponseError("Gemini model catalog exceeded the pagination limit")

    async def _test_gateway_completion(self, settings: GatewaySettings, api_key: str) -> tuple[str, ...]:
        from ClipAI.core.models import LLMMessage, LLMRequest

        if not settings.model.strip():
            raise ProviderResponseError("Gateway does not list models. Enter a model ID to validate Chat Completions.")
        request = LLMRequest((LLMMessage("user", "Reply with OK."),), settings.model, 0.0)
        response = await self._transport.post(
            f"{normalize_gateway_base_url(settings.base_url)}/chat/completions",
            headers=gateway_headers(api_key),
            json=OpenAICompatibleGatewayProvider.to_payload(request),
            timeout=settings.timeout_sec,
        )
        self._raise_for_status("Gateway", response)
        if not OpenAICompatibleGatewayProvider.extract_text(response.payload).strip():
            raise ProviderResponseError("Gateway returned an invalid Chat Completions response")
        return (settings.model,)

    @staticmethod
    def _raise_for_status(name: str, response: HttpResponse) -> None:
        if response.status_code in {401, 403}:
            raise ProviderAuthError(f"{name} rejected the API key")
        if response.status_code >= 400:
            raise ProviderResponseError(f"{name} validation failed with HTTP {response.status_code}")
        if not isinstance(response.payload, dict):
            raise ProviderResponseError(f"{name} returned invalid model metadata")


def _data_models(payload: Any) -> tuple[str, ...]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ProviderResponseError("Provider returned invalid model metadata")
    return _unique_ids(payload["data"], "id")


def _gemini_models(payload: Any) -> tuple[str, ...]:
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
        raise ProviderResponseError("Gemini returned invalid model metadata")
    values = []
    for item in payload["models"]:
        if not isinstance(item, dict):
            continue
        methods = item.get("supportedGenerationMethods")
        if isinstance(methods, list) and "generateContent" not in methods:
            continue
        name = str(item.get("name") or "")
        if name.startswith("models/"):
            name = name[7:]
        if name:
            values.append(name)
    return tuple(dict.fromkeys(values))


def _unique_ids(items: list[Any], field: str) -> tuple[str, ...]:
    values = [str(item.get(field) or "") for item in items if isinstance(item, dict)]
    return tuple(dict.fromkeys(value for value in values if value))
