from __future__ import annotations

from typing import Any

from clipai.providers.azure_openai import AzureOpenAIProvider
from clipai.providers.gemini import GeminiProvider
from clipai.providers.olama import OllamaProvider
from clipai.providers.openai_compact import OpenAICompactProvider


def build_provider(config: dict[str, Any]):
    provider_name = (config.get("provider") or "ollama").lower()
    if provider_name == "ollama":
        return OllamaProvider(config)
    if provider_name == "olama":
        return OllamaProvider(config)
    if provider_name == "gemini":
        return GeminiProvider(config)
    if provider_name == "azure_openai":
        return AzureOpenAIProvider(config)
    if provider_name == "openai":
        return OpenAICompactProvider(config)
    if provider_name == "openai_compact":
        return OpenAICompactProvider(config)
    raise ValueError(f"unsupported provider: {provider_name}")


def create_provider(config: dict[str, Any]):
    return build_provider(config)
