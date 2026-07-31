from __future__ import annotations

import base64
from typing import Any

from ClipAI.core.errors import CancelledError, ProviderAuthError, ProviderResponseError
from ClipAI.core.models import ImageContent, LLMCompleted, LLMProviderEvent, LLMRequest, LLMResult, LLMTextDelta, LLMUsage, TextContent
from ClipAI.core.state import CancellationToken
from ClipAI.providers.http_transport import HttpResponse, HttpTransport
from ClipAI.providers.settings import OpenAISettings, ProviderCredential
from ClipAI.providers.streaming import iter_json_events


class OpenAIProvider:
    """Synchronous text adapter for the OpenAI Responses API."""

    def __init__(self, settings: OpenAISettings, credential: ProviderCredential, transport: HttpTransport) -> None:
        self._settings = settings
        self._credential = credential
        self._transport = transport

    async def execute(self, request: LLMRequest, cancellation: CancellationToken, *, stream: bool):
        if cancellation.is_cancelled:
            raise CancelledError("request cancelled")
        api_key = self._credential.value
        if not api_key:
            raise ProviderAuthError(f"missing API key in {self._settings.api_key_env}")
        payload = self.to_payload(request)
        if stream:
            payload["stream"] = True
            text = ""
            finish_reason: str | None = None
            usage = LLMUsage()
            async with self._transport.stream_lines(
                f"{self._settings.base_url.rstrip('/')}/v1/responses",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=self._settings.timeout_sec,
            ) as response:
                if response.status_code >= 400:
                    _raise_for_status(HttpResponse(response.status_code, "", None))
                async for event in iter_json_events(response.lines):
                    if cancellation.is_cancelled:
                        raise CancelledError("request cancelled")
                    if event.get("type") == "response.output_text.delta":
                        delta = str(event.get("delta") or "")
                        if delta:
                            text += delta
                            yield LLMTextDelta(delta)
                    elif event.get("type") == "response.completed":
                        completed = event.get("response") or {}
                        finish_reason = str(completed.get("status") or "") or None
                        raw_usage = completed.get("usage") or {}
                        usage = LLMUsage(_optional_int(raw_usage.get("input_tokens")), _optional_int(raw_usage.get("output_tokens")))
            if not text.strip():
                raise ProviderResponseError("OpenAI returned an empty response")
            yield LLMCompleted(LLMResult(text.strip(), "openai", request.model, finish_reason, usage))
            return
        response = await self._transport.post(
            f"{self._settings.base_url.rstrip('/')}/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=self.to_payload(request),
            timeout=self._settings.timeout_sec,
        )
        if _contains_image(request) and response.status_code in {400, 404, 422}:
            raise ProviderResponseError("This model could not accept the clipboard image. Switch to a multimodal model and try again.")
        _raise_for_status(response)
        text = self.extract_text(response.payload).strip()
        if not text:
            raise ProviderResponseError("OpenAI returned an empty response")
        usage = response.payload.get("usage") or {}
        yield LLMCompleted(LLMResult(
            text=text,
            provider="openai",
            model=request.model,
            finish_reason=str(response.payload.get("status") or "") or None,
            usage=LLMUsage(
                input_tokens=_optional_int(usage.get("input_tokens")),
                output_tokens=_optional_int(usage.get("output_tokens")),
            ),
        ))

    @staticmethod
    def to_payload(request: LLMRequest) -> dict[str, Any]:
        system_text = "\n\n".join(_text_only(message.content) for message in request.messages if message.role == "system").strip()
        payload: dict[str, Any] = {
            "model": request.model,
            "input": [
                {"role": message.role, "content": _openai_content(message.content)}
                for message in request.messages
                if message.role != "system"
            ],
            "temperature": request.temperature,
        }
        if system_text:
            payload["instructions"] = system_text
        return payload

    @staticmethod
    def extract_text(payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
        texts: list[str] = []
        for item in payload.get("output") or []:
            if item.get("type") != "message":
                continue
            for content in item.get("content") or []:
                if content.get("type") == "output_text":
                    texts.append(str(content.get("text") or ""))
        return "".join(texts)


def _text_only(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(part.text for part in content if isinstance(part, TextContent))


def _openai_content(content):
    if isinstance(content, str):
        return content
    parts = []
    for part in content:
        if isinstance(part, TextContent):
            parts.append({"type": "input_text", "text": part.text})
        elif isinstance(part, ImageContent):
            encoded = base64.b64encode(part.data).decode("ascii")
            parts.append({"type": "input_image", "image_url": f"data:{part.mime_type};base64,{encoded}"})
    return parts


def _contains_image(request: LLMRequest) -> bool:
    return any(not isinstance(message.content, str) and any(isinstance(part, ImageContent) for part in message.content) for message in request.messages)

def _raise_for_status(response: HttpResponse) -> None:
    if response.status_code < 400:
        if not isinstance(response.payload, dict):
            raise ProviderResponseError("OpenAI returned invalid JSON")
        return
    if response.status_code in {401, 403}:
        raise ProviderAuthError("OpenAI rejected the API key")
    detail = response.text.strip().replace("\n", " ")[:200]
    raise ProviderResponseError(f"OpenAI HTTP {response.status_code}: {detail or 'request failed'}")


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) else None
