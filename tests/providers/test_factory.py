from __future__ import annotations

from ClipAI.providers.factory import create_provider
from ClipAI.providers.fake import FakeProvider
from ClipAI.providers.gemini import GeminiProvider


def test_factory_creates_fake_provider() -> None:
    provider = create_provider({"provider": "fake"})

    assert isinstance(provider, FakeProvider)


def test_factory_creates_gemini_provider() -> None:
    provider = create_provider({"provider": "gemini", "gemini_api_key": "test-key"})

    assert isinstance(provider, GeminiProvider)
