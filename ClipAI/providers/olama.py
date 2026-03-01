from __future__ import annotations

import json
from typing import Any, Generator, Iterable

import requests

from ClipAI.core.cancellation import CancellationToken
from ClipAI.core.llm_provider import (
    LLMCancelledError,
    LLMConnectionError,
    LLMProvider,
    LLMResponseError,
    ProviderChunk,
    ProviderResult,
    map_http_error,
)


class OlamaProvider(LLMProvider):
    def __init__(self, config: dict[str, Any]) -> None:
        self._base_url = config.get("olama_base_url", "http://localhost:11434")

    def chat_completion(
        self,
        messages: Iterable[dict[str, Any]],
        model: str,
        stream: bool,
        temperature: float,
        image_base64: str | None,
        cancellation_token: CancellationToken | None,
        **kwargs: Any,
    ) -> Generator[ProviderChunk, None, ProviderResult]:
        url = f"{self._base_url}/api/chat"
        payload = {
            "model": model,
            "stream": stream,
            "messages": list(messages),
            "options": {"temperature": temperature},
        }
        if image_base64:
            payload["images"] = [image_base64]

        full_text: list[str] = []
        try:
            with requests.post(url, json=payload, stream=True, timeout=120) as resp:
                if resp.status_code >= 400:
                    retry_after = self._parse_retry_after(resp.headers.get("Retry-After"))
                    raise map_http_error(resp.status_code, resp.text, retry_after=retry_after)

                if stream:
                    for line in resp.iter_lines(decode_unicode=True):
                        if cancellation_token and cancellation_token.is_cancelled():
                            raise LLMCancelledError("olama request cancelled")
                        if not line:
                            continue
                        data = json.loads(line)
                        text = str((data.get("message") or {}).get("content", ""))
                        if text:
                            full_text.append(text)
                            yield ProviderChunk(content=text, raw=data)
                else:
                    if cancellation_token and cancellation_token.is_cancelled():
                        raise LLMCancelledError("olama request cancelled")
                    data = resp.json()
                    text = str((data.get("message") or {}).get("content", ""))
                    full_text.append(text)
                    yield ProviderChunk(content=text, raw=data)
        except requests.exceptions.Timeout as exc:
            raise LLMConnectionError(str(exc)) from exc
        except requests.exceptions.ConnectionError as exc:
            raise LLMConnectionError(str(exc)) from exc
        except json.JSONDecodeError as exc:
            raise LLMResponseError(f"invalid Olama JSON: {exc}") from exc

        return ProviderResult(content="".join(full_text), usage=None)

    @staticmethod
    def _parse_retry_after(value: str | None) -> float | None:
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None
