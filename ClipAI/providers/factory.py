from __future__ import annotations

from typing import Any

from ClipAI.providers.azure_openai import AzureOpenAIProvider
from ClipAI.providers.gemini import GeminiProvider
from ClipAI.providers.olama import OlamaProvider
from ClipAI.providers.openai_compact import OpenAICompactProvider


def build_provider(config: dict[str, Any]):
    provider_name = (config.get("provider") or "gemini").lower()
    if provider_name == "gemini":
        return GeminiProvider(config)
    if provider_name == "olama":
        return OlamaProvider(config)
    if provider_name == "azure_openai":
        return AzureOpenAIProvider(config)
    if provider_name == "openai_compact":
        return OpenAICompactProvider(config)
    raise ValueError(f"unsupported provider: {provider_name}")
