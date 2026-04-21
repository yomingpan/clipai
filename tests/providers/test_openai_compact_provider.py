from __future__ import annotations

import json
from typing import Any

import pytest

from clipai.core.llm_provider import LLMResponseError
from clipai.providers.openai_compact import OpenAICompactProvider


class _FakeResponse:
    def __init__(self, status_code: int, lines: list[str] | None = None, payload: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._lines = lines or []
        self._payload = payload or {}
        self.headers: dict[str, str] = {}
        self.text = json.dumps(self._payload)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def iter_lines(self, decode_unicode: bool = True):
        del decode_unicode
        for line in self._lines:
            yield line

    def json(self) -> dict[str, Any]:
        return self._payload


def test_openai_requires_api_key() -> None:
    provider = OpenAICompactProvider({})
    gen = provider.chat_completion(
        messages=[{"role": "user", "content": "hi"}],
        model="gpt-4o-mini",
        stream=False,
        temperature=0.2,
        image_base64=None,
        cancellation_token=None,
    )
    with pytest.raises(LLMResponseError):
        next(gen)


def test_openai_list_models(monkeypatch) -> None:
    provider = OpenAICompactProvider({"openai_api_key": "test-key"})

    monkeypatch.setattr(
        "requests.get",
        lambda *args, **kwargs: _FakeResponse(
            200,
            payload={"data": [{"id": "gpt-4o-mini"}, {"id": "gpt-5-mini"}]},
        ),
    )

    assert provider.list_models() == ["gpt-4o-mini", "gpt-5-mini"]


def test_openai_non_stream_completion(monkeypatch) -> None:
    provider = OpenAICompactProvider({"openai_api_key": "test-key"})
    captured: dict[str, Any] = {}

    def fake_post(*args, **kwargs):
        captured["json"] = kwargs["json"]
        return _FakeResponse(
            200,
            payload={
                "choices": [
                    {
                        "message": {
                            "content": "Hello from OpenAI",
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr("requests.post", fake_post)

    gen = provider.chat_completion(
        messages=[{"role": "system", "content": "be concise"}, {"role": "user", "content": "hi"}],
        model="gpt-4o-mini",
        stream=False,
        temperature=0.2,
        image_base64="abc123",
        cancellation_token=None,
    )
    chunks = list(gen)

    assert [chunk.content for chunk in chunks] == ["Hello from OpenAI"]
    assert captured["json"]["messages"][1]["content"][1]["type"] == "image_url"


def test_openai_stream_completion(monkeypatch) -> None:
    provider = OpenAICompactProvider({"openai_api_key": "test-key"})
    lines = [
        'data: {"choices":[{"delta":{"content":"Hello"}}]}',
        'data: {"choices":[{"delta":{"content":" world"}}]}',
        "data: [DONE]",
    ]

    monkeypatch.setattr("requests.post", lambda *args, **kwargs: _FakeResponse(200, lines=lines))

    gen = provider.chat_completion(
        messages=[{"role": "user", "content": "hi"}],
        model="gpt-4o-mini",
        stream=True,
        temperature=0.2,
        image_base64=None,
        cancellation_token=None,
    )

    assert [chunk.content for chunk in gen] == ["Hello", " world"]
