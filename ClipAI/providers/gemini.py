from __future__ import annotations

import json
import queue
import threading
from typing import Any, Generator, Iterable

import aiohttp

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


class GeminiProvider(LLMProvider):
    def __init__(self, config: dict[str, Any]) -> None:
        self._api_key = config.get("gemini_api_key") or config.get("api_key")
        self._base_url = config.get("gemini_base_url", "https://generativelanguage.googleapis.com")

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
        if not self._api_key:
            raise LLMResponseError("missing Gemini API key")

        q: queue.Queue[tuple[str, Any]] = queue.Queue()

        def worker() -> None:
            import asyncio

            asyncio.run(
                self._run_request(
                    q=q,
                    messages=list(messages),
                    model=model,
                    stream=stream,
                    temperature=temperature,
                    image_base64=image_base64,
                    cancellation_token=cancellation_token,
                )
            )

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        full_text: list[str] = []
        while True:
            item_type, data = q.get()
            if item_type == "chunk":
                full_text.append(data)
                yield ProviderChunk(content=data)
                continue
            if item_type == "error":
                raise data
            if item_type == "done":
                return ProviderResult(content="".join(full_text), usage=None)

    async def _run_request(
        self,
        *,
        q: queue.Queue[tuple[str, Any]],
        messages: list[dict[str, Any]],
        model: str,
        stream: bool,
        temperature: float,
        image_base64: str | None,
        cancellation_token: CancellationToken | None,
    ) -> None:
        endpoint = "streamGenerateContent" if stream else "generateContent"
        if stream:
            url = f"{self._base_url}/v1beta/models/{model}:{endpoint}?alt=sse&key={self._api_key}"
        else:
            url = f"{self._base_url}/v1beta/models/{model}:{endpoint}?key={self._api_key}"
        payload = {
            "contents": [self._to_content_parts(messages, image_base64)],
            "generationConfig": {"temperature": temperature},
        }

        timeout = aiohttp.ClientTimeout(total=120)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status >= 400:
                        retry_after = self._parse_retry_after(resp.headers.get("Retry-After"))
                        text = await resp.text()
                        q.put(("error", map_http_error(resp.status, text, retry_after=retry_after)))
                        return

                    if stream:
                        buffer = ""
                        async for raw_chunk in resp.content.iter_any():
                            if cancellation_token and cancellation_token.is_cancelled():
                                q.put(("error", LLMCancelledError("gemini request cancelled")))
                                return
                            buffer += raw_chunk.decode("utf-8", errors="ignore")
                            while "\n\n" in buffer:
                                raw_event, buffer = buffer.split("\n\n", 1)
                                if self._handle_stream_event(raw_event, q):
                                    q.put(("done", None))
                                    return
                        if buffer.strip():
                            if self._handle_stream_event(buffer, q):
                                q.put(("done", None))
                                return
                    else:
                        if cancellation_token and cancellation_token.is_cancelled():
                            q.put(("error", LLMCancelledError("gemini request cancelled")))
                            return
                        obj = await resp.json(content_type=None)
                        text = self._extract_text(obj)
                        q.put(("chunk", text))
            q.put(("done", None))
        except aiohttp.ClientConnectionError as exc:
            q.put(("error", LLMConnectionError(str(exc))))
        except aiohttp.ClientError as exc:
            q.put(("error", LLMConnectionError(str(exc))))

    @staticmethod
    def _to_content_parts(messages: list[dict[str, Any]], image_base64: str | None) -> dict[str, Any]:
        joined = "\n".join(str(m.get("content", "")) for m in messages)
        parts: list[dict[str, Any]] = [{"text": joined}]
        if image_base64:
            parts.append({"inline_data": {"mime_type": "image/png", "data": image_base64}})
        return {"role": "user", "parts": parts}

    @staticmethod
    def _parse_retry_after(value: str | None) -> float | None:
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    @classmethod
    def _handle_stream_event(cls, raw_event: str, q: queue.Queue[tuple[str, Any]]) -> bool:
        lines = [line.strip() for line in raw_event.splitlines() if line.strip()]
        if not lines:
            return False

        data_lines = [line[5:].strip() for line in lines if line.startswith("data:")]
        payloads = data_lines if data_lines else [raw_event.strip()]

        for payload in payloads:
            if not payload:
                continue
            if payload == "[DONE]":
                return True

            try:
                obj = json.loads(payload)
            except json.JSONDecodeError as exc:
                q.put(("error", LLMResponseError(f"invalid Gemini stream JSON: {exc}")))
                return True

            text = cls._extract_text(obj)
            if text:
                q.put(("chunk", text))
        return False

    @staticmethod
    def _extract_text(obj: Any) -> str:
        try:
            if isinstance(obj, list):
                return "".join(GeminiProvider._extract_text(item) for item in obj)
            candidates = obj.get("candidates") or []
            parts = candidates[0]["content"]["parts"]
            return "".join(str(p.get("text", "")) for p in parts)
        except Exception:
            return ""
