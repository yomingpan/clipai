from __future__ import annotations

import pytest

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
