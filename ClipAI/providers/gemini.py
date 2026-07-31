from __future__ import annotations

import base64
from typing import Any

from ClipAI.core.errors import CancelledError, ProviderAuthError, ProviderResponseError
from ClipAI.core.models import ImageContent, LLMCompleted, LLMRequest, LLMResult, LLMTextDelta, LLMUsage, TextContent
from ClipAI.core.state import CancellationToken
from ClipAI.providers.http_transport import HttpResponse, HttpTransport
from ClipAI.providers.settings import GeminiSettings, ProviderCredential
from ClipAI.providers.streaming import iter_json_events


class GeminiProvider:
    def __init__(self, settings: GeminiSettings, credential: ProviderCredential, transport: HttpTransport) -> None:
        self._settings = settings
        self._credential = credential
        self._transport = transport

    async def execute(self, request: LLMRequest, cancellation: CancellationToken, *, stream: bool):
        if cancellation.is_cancelled:
            raise CancelledError("request cancelled")
        api_key = self._credential.value
        if not api_key:
            raise ProviderAuthError(f"missing API key in {self._settings.api_key_env}")
        if stream:
            text = ""
            finish_reason: str | None = None
            usage = LLMUsage()
            async with self._transport.stream_lines(
                f"{self._settings.base_url.rstrip('/')}/v1beta/models/{request.model}:streamGenerateContent",
                params={"key": api_key, "alt": "sse"},
                json=self.to_payload(request),
                timeout=self._settings.timeout_sec,
            ) as response:
                if response.status_code >= 400:
                    _raise_for_status("Gemini", HttpResponse(response.status_code, "", None))
                async for event in iter_json_events(response.lines):
                    if cancellation.is_cancelled:
                        raise CancelledError("request cancelled")
                    delta = self.extract_text(event)
                    if delta:
                        text += delta
                        yield LLMTextDelta(delta)
                    finish_reason = self._finish_reason(event) or finish_reason
                    raw_usage = event.get("usageMetadata") or {}
                    if raw_usage:
                        usage = LLMUsage(_optional_int(raw_usage.get("promptTokenCount")), _optional_int(raw_usage.get("candidatesTokenCount")))
            if not text.strip():
                raise ProviderResponseError("Gemini returned an empty response")
            yield LLMCompleted(LLMResult(text.strip(), "gemini", request.model, finish_reason, usage))
            return
        response = await self._transport.post(
            f"{self._settings.base_url.rstrip('/')}/v1beta/models/{request.model}:generateContent",
            params={"key": api_key},
            json=self.to_payload(request),
            timeout=self._settings.timeout_sec,
        )
        if _contains_image(request) and response.status_code in {400, 404, 422}:
            raise ProviderResponseError("This model could not accept the clipboard image. Switch to a multimodal model and try again.")
        _raise_for_status("Gemini", response)
        text = self.extract_text(response.payload).strip()
        if not text:
            raise ProviderResponseError("Gemini returned an empty response")
        usage_data = response.payload.get("usageMetadata") or {} if isinstance(response.payload, dict) else {}
        yield LLMCompleted(LLMResult(
            text=text,
            provider="gemini",
            model=request.model,
            finish_reason=self._finish_reason(response.payload),
            usage=LLMUsage(
                input_tokens=_optional_int(usage_data.get("promptTokenCount")),
                output_tokens=_optional_int(usage_data.get("candidatesTokenCount")),
            ),
        ))

    @staticmethod
    def to_payload(request: LLMRequest) -> dict[str, Any]:
        system_text = "\n\n".join(_text_only(message.content) for message in request.messages if message.role == "system").strip()
        contents = [
            {"role": "model" if message.role == "assistant" else "user", "parts": _gemini_parts(message.content)}
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


def _text_only(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(part.text for part in content if isinstance(part, TextContent))


def _gemini_parts(content):
    if isinstance(content, str):
        return [{"text": content}]
    parts = []
    for part in content:
        if isinstance(part, TextContent):
            parts.append({"text": part.text})
        elif isinstance(part, ImageContent):
            parts.append({"inline_data": {"mime_type": part.mime_type, "data": base64.b64encode(part.data).decode("ascii")}})
    return parts


def _contains_image(request: LLMRequest) -> bool:
    return any(not isinstance(message.content, str) and any(isinstance(part, ImageContent) for part in message.content) for message in request.messages)

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
