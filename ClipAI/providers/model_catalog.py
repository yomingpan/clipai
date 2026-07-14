from __future__ import annotations

from typing import Any

from ClipAI.core.errors import ProviderAuthError, ProviderResponseError
from ClipAI.providers.http_transport import HttpResponse, HttpTransport, RequestsHttpTransport
from ClipAI.providers.settings import AnthropicSettings, GeminiSettings, OpenAISettings, ProviderSettings


class ProviderModelCatalogClient:
    def __init__(self, transport: HttpTransport | None = None) -> None:
        self._transport = transport or RequestsHttpTransport()

    def list_models(self, provider_id: str, settings: ProviderSettings, api_key: str) -> tuple[str, ...]:
        if not api_key.strip():
            raise ProviderAuthError("API key is required")
        if provider_id == "gemini" and isinstance(settings, GeminiSettings):
            response = self._transport.get(
                f"{settings.base_url.rstrip('/')}/v1beta/models",
                params={"key": api_key},
                timeout=settings.timeout_sec,
            )
            self._raise_for_status("Gemini", response)
            return _gemini_models(response.payload)
        if provider_id == "openai" and isinstance(settings, OpenAISettings):
            response = self._transport.get(
                f"{settings.base_url.rstrip('/')}/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=settings.timeout_sec,
            )
            self._raise_for_status("OpenAI", response)
            return _data_models(response.payload)
        if provider_id == "anthropic" and isinstance(settings, AnthropicSettings):
            response = self._transport.get(
                f"{settings.base_url.rstrip('/')}/v1/models",
                headers={"x-api-key": api_key, "anthropic-version": settings.api_version},
                timeout=settings.timeout_sec,
            )
            self._raise_for_status("Anthropic", response)
            return _data_models(response.payload)
        raise ProviderResponseError("Unsupported provider configuration")

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
        name = str(item.get("name") or "")
        if name.startswith("models/"):
            name = name[7:]
        if name:
            values.append(name)
    return tuple(dict.fromkeys(values))


def _unique_ids(items: list[Any], field: str) -> tuple[str, ...]:
    values = [str(item.get(field) or "") for item in items if isinstance(item, dict)]
    return tuple(dict.fromkeys(value for value in values if value))
