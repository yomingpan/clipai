from __future__ import annotations

from typing import Any

from ClipAI.core.errors import CancelledError, ProviderAuthError, ProviderResponseError
from ClipAI.core.models import LLMRequest, LLMResult, LLMUsage
from ClipAI.core.state import CancellationToken
from ClipAI.providers.http_transport import HttpResponse, HttpTransport, RequestsHttpTransport
from ClipAI.providers.settings import GeminiSettings, ProviderCredential


class GeminiProvider:
    def __init__(self, settings: GeminiSettings, credential: ProviderCredential, transport: HttpTransport | None = None) -> None:
        self._settings = settings
        self._credential = credential
        self._transport = transport or RequestsHttpTransport()

    def complete(self, request: LLMRequest, cancellation: CancellationToken) -> LLMResult:
        if cancellation.is_cancelled:
            raise CancelledError("request cancelled")
        api_key = self._credential.value
        if not api_key:
            raise ProviderAuthError(f"missing API key in {self._settings.api_key_env}")
        response = self._transport.post(
            f"{self._settings.base_url.rstrip('/')}/v1beta/models/{request.model}:generateContent",
            params={"key": api_key},
            json=self.to_payload(request),
            timeout=self._settings.timeout_sec,
        )
        _raise_for_status("Gemini", response)
        text = self.extract_text(response.payload).strip()
        if not text:
            raise ProviderResponseError("Gemini returned an empty response")
        usage_data = response.payload.get("usageMetadata") or {} if isinstance(response.payload, dict) else {}
        return LLMResult(
            text=text,
            provider="gemini",
            model=request.model,
            finish_reason=self._finish_reason(response.payload),
            usage=LLMUsage(
                input_tokens=_optional_int(usage_data.get("promptTokenCount")),
                output_tokens=_optional_int(usage_data.get("candidatesTokenCount")),
            ),
        )

    @staticmethod
    def to_payload(request: LLMRequest) -> dict[str, Any]:
        system_text = "\n\n".join(message.content for message in request.messages if message.role == "system").strip()
        contents = [
            {"role": "model" if message.role == "assistant" else "user", "parts": [{"text": message.content}]}
            for message in request.messages
            if message.role != "system"
        ]
        payload: dict[str, Any] = {"contents": contents, "generationConfig": {"temperature": request.temperature}}
        if system_text:
            payload["systemInstruction"] = {"parts": [{"text": system_text}]}
        return payload

    @staticmethod
    def extract_text(payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
        texts: list[str] = []
        for candidate in payload.get("candidates") or []:
            for part in (candidate.get("content") or {}).get("parts") or []:
                texts.append(str(part.get("text") or ""))
        return "".join(texts)

    @staticmethod
    def _finish_reason(payload: Any) -> str | None:
        if not isinstance(payload, dict) or not payload.get("candidates"):
            return None
        return str(payload["candidates"][0].get("finishReason") or "") or None


def _raise_for_status(name: str, response: HttpResponse) -> None:
    if response.status_code < 400:
        if response.payload is None:
            raise ProviderResponseError(f"{name} returned invalid JSON")
        return
    if response.status_code in {401, 403}:
        raise ProviderAuthError(f"{name} rejected the API key")
    detail = response.text.strip().replace("\n", " ")
    if len(detail) > 200:
        detail = f"{detail[:199]}..."
    raise ProviderResponseError(f"{name} HTTP {response.status_code}: {detail or 'request failed'}")


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) else None
