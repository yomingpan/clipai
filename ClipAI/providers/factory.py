from __future__ import annotations

from typing import Any

from ClipAI.providers.fake import FakeProvider
from ClipAI.providers.gemini import GeminiProvider


def build_provider(config: dict[str, Any] | None = None):
    provider_name = ((config or {}).get("provider") or "fake").lower()
    if provider_name == "fake":
        return FakeProvider()
    if provider_name == "gemini":
        return GeminiProvider(config)
    raise ValueError(f"unsupported provider: {provider_name}")


def create_provider(config: dict[str, Any] | None = None):
    return build_provider(config)
