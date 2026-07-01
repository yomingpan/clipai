from __future__ import annotations

import pytest
import requests

from ClipAI.core.provider import ProviderConfigurationError, ProviderRequest, ProviderResponseError
from ClipAI.providers.gemini import GeminiProvider


class FakeResponse:
    def __init__(self, *, status_code: int = 200, payload=None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def make_request() -> ProviderRequest:
    return ProviderRequest(
        messages=[
            {"role": "system", "content": "You are concise."},
            {"role": "user", "content": "Explain appetizer."},
        ],
        model="gemini-test",
        temperature=0.2,
    )


def test_gemini_payload_maps_system_and_user_messages() -> None:
    payload = GeminiProvider.to_payload(make_request())

    assert payload["systemInstruction"] == {"parts": [{"text": "You are concise."}]}
    assert payload["contents"] == [
        {"role": "user", "parts": [{"text": "Explain appetizer."}]}
    ]
    assert payload["generationConfig"] == {"temperature": 0.2}


def test_gemini_extracts_text_from_valid_response() -> None:
    payload = {
        "candidates": [
            {"content": {"parts": [{"text": "hello "}, {"text": "world"}]}}
        ]
    }

    assert GeminiProvider.extract_text(payload) == "hello world"


def test_missing_api_key_raises_readable_error(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    provider = GeminiProvider({})

    with pytest.raises(ProviderConfigurationError, match="missing Gemini API key"):
        provider.complete(make_request())


def test_http_error_raises_readable_error(monkeypatch) -> None:
    def fake_post(*args, **kwargs):
        return FakeResponse(status_code=403, text="denied")

    monkeypatch.setattr(requests, "post", fake_post)
    provider = GeminiProvider({"gemini_api_key": "key"})

    with pytest.raises(ProviderResponseError, match="Gemini HTTP 403: denied"):
        provider.complete(make_request())


def test_complete_returns_response_text(monkeypatch) -> None:
    calls = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeResponse(
            payload={
                "candidates": [
                    {"content": {"parts": [{"text": "Gemini result"}]}}
                ]
            }
        )

    monkeypatch.setattr(requests, "post", fake_post)
    provider = GeminiProvider({"gemini_api_key": "key", "gemini_base_url": "https://example.test"})

    assert provider.complete(make_request()) == "Gemini result"
    assert calls[0][0][0] == "https://example.test/v1beta/models/gemini-test:generateContent"
    assert calls[0][1]["params"] == {"key": "key"}


def test_empty_response_raises_readable_error(monkeypatch) -> None:
    def fake_post(*args, **kwargs):
        return FakeResponse(payload={"candidates": []})

    monkeypatch.setattr(requests, "post", fake_post)
    provider = GeminiProvider({"gemini_api_key": "key"})

    with pytest.raises(ProviderResponseError, match="Provider returned an empty response."):
        provider.complete(make_request())
