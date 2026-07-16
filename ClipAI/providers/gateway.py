from __future__ import annotations

import base64
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from ClipAI.core.errors import CancelledError, ConfigError, ProviderAuthError, ProviderResponseError
from ClipAI.core.models import ImageContent, LLMRequest, LLMResult, LLMUsage, TextContent
from ClipAI.core.state import CancellationToken
from ClipAI.providers.http_transport import HttpResponse, HttpTransport, RequestsHttpTransport
from ClipAI.providers.settings import GatewaySettings, ProviderCredential


class OpenAICompatibleGatewayProvider:
    def __init__(self, settings: GatewaySettings, credential: ProviderCredential, transport: HttpTransport | None = None) -> None:
        self._settings = settings
        self._credential = credential
        self._transport = transport or RequestsHttpTransport()

    def complete(self, request: LLMRequest, cancellation: CancellationToken) -> LLMResult:
        if cancellation.is_cancelled:
            raise CancelledError("request cancelled")
        response = self._transport.post(
            f"{normalize_gateway_base_url(self._settings.base_url)}/chat/completions",
            headers=gateway_headers(self._credential.value),
            json=self.to_payload(request),
            timeout=self._settings.timeout_sec,
        )
        _raise_for_status(response)
        text = self.extract_text(response.payload).strip()
        if not text:
            raise ProviderResponseError("Gateway returned an empty response")
        choice = response.payload["choices"][0]
        usage = response.payload.get("usage") or {}
        return LLMResult(
            text=text,
            provider="gateway",
            model=request.model,
            finish_reason=str(choice.get("finish_reason") or "") or None,
            usage=LLMUsage(_optional_int(usage.get("prompt_tokens")), _optional_int(usage.get("completion_tokens"))),
        )

    @staticmethod
    def to_payload(request: LLMRequest) -> dict[str, Any]:
        return {
            "model": request.model,
            "messages": [
                {"role": message.role, "content": _chat_content(message.content)}
                for message in request.messages
            ],
            "temperature": request.temperature,
        }

    @staticmethod
    def extract_text(payload: Any) -> str:
        if not isinstance(payload, dict) or not isinstance(payload.get("choices"), list) or not payload["choices"]:
            return ""
        message = payload["choices"][0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
        return ""


def normalize_gateway_base_url(value: str) -> str:
    raw = value.strip().rstrip("/")
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.query or parsed.fragment:
        raise ConfigError("Gateway URL must be an absolute HTTP(S) URL without query parameters or fragments")
    loopback = parsed.hostname == "localhost" or parsed.hostname == "::1" or parsed.hostname.startswith("127.")
    if parsed.scheme == "http" and not loopback:
        raise ConfigError("Remote gateway URLs must use HTTPS")
    path = parsed.path.rstrip("/")
    if not path.endswith("/v1"):
        path = f"{path}/v1" if path else "/v1"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def gateway_headers(api_key: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _chat_content(content):
    if isinstance(content, str):
        return content
    parts = []
    for part in content:
        if isinstance(part, TextContent):
            parts.append({"type": "text", "text": part.text})
        elif isinstance(part, ImageContent):
            encoded = base64.b64encode(part.data).decode("ascii")
            parts.append({"type": "image_url", "image_url": {"url": f"data:{part.mime_type};base64,{encoded}"}})
    return parts


def _raise_for_status(response: HttpResponse) -> None:
    if response.status_code in {401, 403}:
        raise ProviderAuthError("Gateway rejected the API key")
    if response.status_code >= 400:
        raise ProviderResponseError(f"Gateway request failed with HTTP {response.status_code}")
    if not isinstance(response.payload, dict):
        raise ProviderResponseError("Gateway returned invalid JSON")


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) else None
