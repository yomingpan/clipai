from __future__ import annotations

from dataclasses import replace

import pytest

from ClipAI.app.config_loader import load_config_bundle
from ClipAI.app.container import _build_provider
from ClipAI.providers.anthropic import AnthropicProvider
from ClipAI.providers.fake import FakeProvider
from ClipAI.providers.gemini import GeminiProvider
from ClipAI.providers.openai import OpenAIProvider


@pytest.mark.parametrize(
    ("active", "expected_type"),
    [
        ("fake", FakeProvider),
        ("gemini", GeminiProvider),
        ("openai", OpenAIProvider),
        ("anthropic", AnthropicProvider),
    ],
)
def test_container_switches_provider_without_service_changes(active, expected_type) -> None:
    bundle = load_config_bundle()
    bundle = replace(bundle, providers=replace(bundle.providers, active=active))
    provider, model = _build_provider(bundle)
    assert isinstance(provider, expected_type)
    assert model

