from __future__ import annotations

import os
from typing import Any

from ClipAI.core.errors import CancelledError, ProviderAuthError, ProviderResponseError
from ClipAI.core.models import LLMRequest, LLMResult, LLMUsage
from ClipAI.core.state import CancellationToken
from ClipAI.providers.http_transport import HttpResponse, HttpTransport, RequestsHttpTransport
from ClipAI.providers.settings import AnthropicSettings


class AnthropicProvider:
    def __init__(self, settings: AnthropicSettings, transport: HttpTransport | None = None) -> None:
        self._settings = settings
        self._transport = transport or RequestsHttpTransport()

    def complete(self, request: LLMRequest, cancellation: CancellationToken) -> LLMResult:
        if cancellation.is_cancelled:
            raise CancelledError("request cancelled")
        api_key = os.getenv(self._settings.api_key_env)
        if not api_key:
            raise ProviderAuthError(f"missing API key in {self._settings.api_key_env}")
        response = self._transport.post(
            f"{self._settings.base_url.rstrip('/')}/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": self._settings.api_version,
                "content-type": "application/json",
            },
            json=self.to_payload(request),
            timeout=self._settings.timeout_sec,
        )
        _raise_for_status(response)
        text = self.extract_text(response.payload).strip()
        if not text:
            raise ProviderResponseError("Anthropic returned an empty response")
        usage = response.payload.get("usage") or {}
        return LLMResult(
            text=text,
            provider="anthropic",
            model=request.model,
            finish_reason=str(response.payload.get("stop_reason") or "") or None,
            usage=LLMUsage(
                input_tokens=_optional_int(usage.get("input_tokens")),
                output_tokens=_optional_int(usage.get("output_tokens")),
            ),
        )

    def to_payload(self, request: LLMRequest) -> dict[str, Any]:
        system_text = "\n\n".join(message.content for message in request.messages if message.role == "system").strip()
        payload: dict[str, Any] = {
            "model": request.model,
            "max_tokens": self._settings.max_tokens,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request.messages
                if message.role != "system"
            ],
            "temperature": request.temperature,
        }
        if system_text:
            payload["system"] = system_text
        return payload

    @staticmethod
    def extract_text(payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
        return "".join(
            str(block.get("text") or "")
            for block in payload.get("content") or []
            if block.get("type") == "text"
        )


def _raise_for_status(response: HttpResponse) -> None:
    if response.status_code < 400:
        if not isinstance(response.payload, dict):
            raise ProviderResponseError("Anthropic returned invalid JSON")
        return
    if response.status_code in {401, 403}:
        raise ProviderAuthError("Anthropic rejected the API key")
    detail = response.text.strip().replace("\n", " ")[:200]
    raise ProviderResponseError(f"Anthropic HTTP {response.status_code}: {detail or 'request failed'}")


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) else None

