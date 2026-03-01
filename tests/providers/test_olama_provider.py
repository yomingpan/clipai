from __future__ import annotations

import json
from typing import Any

import pytest

from ClipAI.core.cancellation import CancellationController
from ClipAI.core.llm_provider import LLMCancelledError, LLMConnectionError
from ClipAI.providers.olama import OlamaProvider


class _FakeResponse:
    def __init__(self, status_code: int, lines: list[str], text: str = "", headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self._lines = lines
        self.text = text
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def iter_lines(self, decode_unicode: bool = True):
        del decode_unicode
        for line in self._lines:
            yield line

    def json(self) -> dict[str, Any]:
        return {"message": {"content": "single"}}


def test_olama_non_stream_generator(monkeypatch) -> None:
    provider = OlamaProvider({"olama_base_url": "http://localhost:11434"})

    def fake_post(*args, **kwargs):
        del args, kwargs
        return _FakeResponse(200, [])

    monkeypatch.setattr("requests.post", fake_post)
    gen = provider.chat_completion(
        messages=[{"role": "user", "content": "hi"}],
        model="x",
        stream=False,
        temperature=0.2,
        image_base64=None,
        cancellation_token=None,
    )
    chunks = list(gen)
    assert len(chunks) == 1
    assert chunks[0].content == "single"


def test_olama_cancellation(monkeypatch) -> None:
    provider = OlamaProvider({})
    line = json.dumps({"message": {"content": "abc"}})

    def fake_post(*args, **kwargs):
        del args, kwargs
        return _FakeResponse(200, [line])

    monkeypatch.setattr("requests.post", fake_post)

    ctrl = CancellationController()
    ctrl.cancel("stop")
    gen = provider.chat_completion(
        messages=[{"role": "user", "content": "hi"}],
        model="x",
        stream=True,
        temperature=0.2,
        image_base64=None,
        cancellation_token=ctrl.token,
    )
    with pytest.raises(LLMCancelledError):
        next(gen)


def test_olama_connection_error(monkeypatch) -> None:
    provider = OlamaProvider({})

    class _E(Exception):
        pass

    def fake_post(*args, **kwargs):
        import requests

        del args, kwargs
        raise requests.exceptions.ConnectionError("down")

    monkeypatch.setattr("requests.post", fake_post)
    gen = provider.chat_completion(
        messages=[{"role": "user", "content": "hi"}],
        model="x",
        stream=True,
        temperature=0.2,
        image_base64=None,
        cancellation_token=None,
    )
    with pytest.raises(LLMConnectionError):
        list(gen)
