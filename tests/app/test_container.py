from __future__ import annotations

from dataclasses import replace

import pytest

from ClipAI.app.config_loader import load_config_bundle
from ClipAI.app.container import _build_provider, _resolve_active_credential, _resolve_active_model
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


def test_composition_root_resolves_only_the_active_provider_secret(monkeypatch) -> None:
    bundle = load_config_bundle()
    monkeypatch.setenv(bundle.providers.gemini.api_key_env, "secret-value")
    credential = _resolve_active_credential(bundle)
    assert credential is not None
    assert credential.env_name == bundle.providers.gemini.api_key_env
    assert credential.value == "secret-value"
    assert "secret-value" not in repr(credential)


@pytest.mark.parametrize(
    ("active", "env_name", "model"),
    [
        ("gemini", "GEMINI_MODEL", "gemini-env-model"),
        ("openai", "OPENAI_MODEL", "openai-env-model"),
        ("anthropic", "ANTHROPIC_MODEL", "anthropic-env-model"),
    ],
)
def test_composition_root_prefers_dotenv_model_value(monkeypatch, active, env_name, model) -> None:
    bundle = load_config_bundle()
    bundle = replace(bundle, providers=replace(bundle.providers, active=active))
    monkeypatch.setenv(env_name, model)
    assert _resolve_active_model(bundle) == model
    assert _build_provider(bundle)[1] == model


def test_composition_root_uses_yaml_model_without_environment_override(monkeypatch) -> None:
    bundle = load_config_bundle()
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert _resolve_active_model(bundle) == bundle.providers.gemini.model
