from __future__ import annotations

import pytest
import requests

from clipai.core.llm_provider import LLMResponseError
from clipai.providers.gemini import GeminiProvider


def test_gemini_requires_api_key() -> None:
    provider = GeminiProvider({})
    gen = provider.chat_completion(
        messages=[{"role": "user", "content": "hi"}],
        model="gemini-1.5-flash",
        stream=True,
        temperature=0.2,
        image_base64=None,
        cancellation_token=None,
    )
    with pytest.raises(LLMResponseError):
        next(gen)


def test_gemini_list_models_filters_generation_models(monkeypatch) -> None:
    provider = GeminiProvider({"gemini_api_key": "test-key"})

    class _FakeResponse:
        status_code = 200
        headers = {}
        text = ""

        @staticmethod
        def json() -> dict[str, object]:
            return {
                "models": [
                    {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]},
                    {"name": "models/gemini-2.5-pro", "supportedGenerationMethods": ["streamGenerateContent"]},
                ]
            }

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: _FakeResponse())

    assert provider.list_models() == ["gemini-2.5-flash", "gemini-2.5-pro"]
