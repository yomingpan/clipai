from __future__ import annotations

import base64
from typing import Any

from ClipAI.core.errors import CancelledError, ProviderAuthError, ProviderResponseError
from ClipAI.core.models import ImageContent, LLMCompleted, LLMRequest, LLMResult, LLMTextDelta, LLMUsage, TextContent
from ClipAI.core.state import CancellationToken
from ClipAI.providers.http_transport import HttpResponse, HttpTransport
from ClipAI.providers.settings import AnthropicSettings, ProviderCredential
from ClipAI.providers.streaming import iter_json_events


class AnthropicProvider:
    def __init__(self, settings: AnthropicSettings, credential: ProviderCredential, transport: HttpTransport) -> None:
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
            input_tokens: int | None = None
            output_tokens: int | None = None
            async with self._transport.stream_lines(
                f"{self._settings.base_url.rstrip('/')}/v1/messages",
                headers={"x-api-key": api_key, "anthropic-version": self._settings.api_version, "content-type": "application/json"},
                json=payload,
                timeout=self._settings.timeout_sec,
            ) as response:
                if response.status_code >= 400:
                    _raise_for_status(HttpResponse(response.status_code, "", None))
                async for event in iter_json_events(response.lines):
                    if cancellation.is_cancelled:
                        raise CancelledError("request cancelled")
                    event_type = event.get("type")
                    if event_type == "content_block_delta":
                        delta = str((event.get("delta") or {}).get("text") or "")
                        if delta:
                            text += delta
                            yield LLMTextDelta(delta)
                    elif event_type == "message_start":
                        input_tokens = _optional_int(((event.get("message") or {}).get("usage") or {}).get("input_tokens"))
                    elif event_type == "message_delta":
                        finish_reason = str((event.get("delta") or {}).get("stop_reason") or "") or finish_reason
                        output_tokens = _optional_int((event.get("usage") or {}).get("output_tokens"))
            if not text.strip():
                raise ProviderResponseError("Anthropic returned an empty response")
            yield LLMCompleted(LLMResult(text.strip(), "anthropic", request.model, finish_reason, LLMUsage(input_tokens, output_tokens)))
            return
        response = await self._transport.post(
            f"{self._settings.base_url.rstrip('/')}/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": self._settings.api_version,
                "content-type": "application/json",
            },
            json=payload,
            timeout=self._settings.timeout_sec,
        )
        if _contains_image(request) and response.status_code in {400, 404, 422}:
            raise ProviderResponseError("This model could not accept the clipboard image. Switch to a multimodal model and try again.")
        _raise_for_status(response)
        text = self.extract_text(response.payload).strip()
        if not text:
            raise ProviderResponseError("Anthropic returned an empty response")
        usage = response.payload.get("usage") or {}
        yield LLMCompleted(LLMResult(
            text=text,
            provider="anthropic",
            model=request.model,
            finish_reason=str(response.payload.get("stop_reason") or "") or None,
            usage=LLMUsage(
                input_tokens=_optional_int(usage.get("input_tokens")),
                output_tokens=_optional_int(usage.get("output_tokens")),
            ),
        ))

    def to_payload(self, request: LLMRequest) -> dict[str, Any]:
        system_text = "\n\n".join(_text_only(message.content) for message in request.messages if message.role == "system").strip()
        payload: dict[str, Any] = {
            "model": request.model,
            "max_tokens": self._settings.max_tokens,
            "messages": [
                {"role": message.role, "content": _anthropic_content(message.content)}
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


def _text_only(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(part.text for part in content if isinstance(part, TextContent))


def _anthropic_content(content):
    if isinstance(content, str):
        return content
    parts = []
    for part in content:
        if isinstance(part, TextContent):
            parts.append({"type": "text", "text": part.text})
        elif isinstance(part, ImageContent):
            parts.append({"type": "image", "source": {"type": "base64", "media_type": part.mime_type, "data": base64.b64encode(part.data).decode("ascii")}})
    return parts


def _contains_image(request: LLMRequest) -> bool:
    return any(not isinstance(message.content, str) and any(isinstance(part, ImageContent) for part in message.content) for message in request.messages)

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
