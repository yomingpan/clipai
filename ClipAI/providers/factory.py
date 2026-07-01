from __future__ import annotations

from typing import Any

from ClipAI.providers.fake import FakeProvider


def build_provider(config: dict[str, Any] | None = None):
    provider_name = ((config or {}).get("provider") or "fake").lower()
    if provider_name == "fake":
        return FakeProvider()
    raise ValueError(f"phase 3 runtime only supports fake provider, got: {provider_name}")


def create_provider(config: dict[str, Any] | None = None):
    return build_provider(config)
