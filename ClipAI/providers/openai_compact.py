from __future__ import annotations

import json
import os
from typing import Any, Generator, Iterable

import requests

from clipai.core.cancellation import CancellationToken
from clipai.core.llm_provider import (
    LLMCancelledError,
    LLMConnectionError,
    LLMProvider,
    LLMResponseError,
    ProviderChunk,
    ProviderResult,
    map_http_error,
)


class OpenAICompactProvider(LLMProvider):
    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._api_key = (
            config.get("openai_api_key")
            or config.get("api_key")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("LLM_API_KEY")
        )
        self._base_url = (
            config.get("openai_base_url")
            or os.getenv("OPENAI_BASE_URL")
            or "https://api.openai.com"
        ).rstrip("/")

    def list_models(self) -> list[str]:
        if not self._api_key:
            raise LLMResponseError("missing OpenAI API key")

        url = f"{self._base_url}/v1/models"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=30)
        except requests.exceptions.Timeout as exc:
            raise LLMConnectionError(str(exc)) from exc
        except requests.exceptions.ConnectionError as exc:
            raise LLMConnectionError(str(exc)) from exc

        if resp.status_code >= 400:
            retry_after = self._parse_retry_after(resp.headers.get("Retry-After"))
            raise map_http_error(resp.status_code, resp.text, retry_after=retry_after)

        try:
            payload = resp.json()
        except ValueError as exc:
            raise LLMResponseError(f"invalid OpenAI JSON: {exc}") from exc

        models = []
        for item in payload.get("data") or []:
            model_id = str(item.get("id") or "").strip()
            if model_id and model_id not in models:
                models.append(model_id)
        return models

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
        del kwargs
        if not self._api_key:
            raise LLMResponseError("missing OpenAI API key")

        url = f"{self._base_url}/v1/chat/completions"
        payload = {
            "model": model,
            "messages": self._to_openai_messages(list(messages), image_base64),
            "stream": stream,
            "temperature": temperature,
        }

        full_text: list[str] = []
        try:
            with requests.post(
                url,
                headers=self._headers(),
                json=payload,
                stream=stream,
                timeout=120,
            ) as resp:
                if resp.status_code >= 400:
                    retry_after = self._parse_retry_after(resp.headers.get("Retry-After"))
                    raise map_http_error(resp.status_code, resp.text, retry_after=retry_after)

                if stream:
                    for line in resp.iter_lines(decode_unicode=True):
                        if cancellation_token and cancellation_token.is_cancelled():
                            raise LLMCancelledError("openai request cancelled")
                        if not line:
                            continue
                        text = self._extract_stream_text(line)
                        if text:
                            full_text.append(text)
                            yield ProviderChunk(content=text)
                else:
                    if cancellation_token and cancellation_token.is_cancelled():
                        raise LLMCancelledError("openai request cancelled")
                    data = resp.json()
                    text = self._extract_response_text(data)
                    if text:
                        full_text.append(text)
                        yield ProviderChunk(content=text, raw=data)
        except requests.exceptions.Timeout as exc:
            raise LLMConnectionError(str(exc)) from exc
        except requests.exceptions.ConnectionError as exc:
            raise LLMConnectionError(str(exc)) from exc
        except json.JSONDecodeError as exc:
            raise LLMResponseError(f"invalid OpenAI JSON: {exc}") from exc

        return ProviderResult(content="".join(full_text), usage=None)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _parse_retry_after(value: str | None) -> float | None:
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    @classmethod
    def _to_openai_messages(
        cls,
        messages: list[dict[str, Any]],
        image_base64: str | None,
    ) -> list[dict[str, Any]]:
        if not image_base64:
            return [
                {
                    "role": str(message.get("role") or "user"),
                    "content": str(message.get("content") or ""),
                }
                for message in messages
            ]

        last_user_index = -1
        for idx, message in enumerate(messages):
            if str(message.get("role") or "user") == "user":
                last_user_index = idx

        out: list[dict[str, Any]] = []
        for idx, message in enumerate(messages):
            role = str(message.get("role") or "user")
            content = str(message.get("content") or "")
            if idx == last_user_index and role == "user":
                out.append(
                    {
                        "role": role,
                        "content": [
                            {"type": "text", "text": content},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                            },
                        ],
                    }
                )
                continue
            out.append({"role": role, "content": content})
        return out

    @classmethod
    def _extract_stream_text(cls, line: str) -> str:
        raw = line.strip()
        if raw.startswith("data:"):
            raw = raw[5:].strip()
        if not raw or raw == "[DONE]":
            return ""
        payload = json.loads(raw)
        choices = payload.get("choices") or []
        if not choices:
            return ""
        delta = choices[0].get("delta") or {}
        return cls._normalize_text_content(delta.get("content"))

    @classmethod
    def _extract_response_text(cls, payload: dict[str, Any]) -> str:
        choices = payload.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return cls._normalize_text_content(message.get("content"))

    @staticmethod
    def _normalize_text_content(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
            return "".join(parts)
        return ""
