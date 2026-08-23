from __future__ import annotations

from dataclasses import replace

import pytest

from ClipAI.app.config_loader import load_config_bundle
from ClipAI.app.container import _build_provider, _build_provider_snapshot, _needs_provider_setup, _resolve_active_credential, _resolve_active_model
from ClipAI.app.provider_configuration import build_provider_snapshot
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
    settings = bundle.providers.active_settings()
    assert settings is not None
    bundle = replace(bundle, providers=replace(bundle.providers, **{active: replace(settings, available_models=(*settings.available_models, model))}))
    monkeypatch.setenv(env_name, model)
    assert _resolve_active_model(bundle) == model
    assert _build_provider(bundle)[1] == model


def test_composition_root_uses_yaml_model_without_environment_override(monkeypatch) -> None:
    bundle = load_config_bundle()
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert _resolve_active_model(bundle) == bundle.providers.gemini.model


def test_composition_root_accepts_dotenv_model_outside_static_catalog(monkeypatch) -> None:
    bundle = load_config_bundle()
    monkeypatch.setenv("GEMINI_MODEL", "unknown-model")
    assert _resolve_active_model(bundle) == "unknown-model"
    snapshot = _build_provider_snapshot(bundle, {"CLIPAI_PROVIDER": "gemini", "GEMINI_API_KEY": "key", "GEMINI_MODEL": "unknown-model"})
    option = next(item for item in snapshot.options if item.provider_id == "gemini")
    assert option.available_models[0] == "unknown-model"


def test_provider_snapshot_uses_dotenv_provider_and_marks_missing_keys() -> None:
    bundle = load_config_bundle()
    snapshot = _build_provider_snapshot(
        bundle,
        {
            "CLIPAI_PROVIDER": "openai",
            "OPENAI_API_KEY": "secret-value",
            "OPENAI_MODEL": "gpt-4.1",
        },
    )
    assert snapshot.active_provider == "openai"
    openai = next(item for item in snapshot.bindings if item.provider_id == "openai")
    gemini = next(item for item in snapshot.bindings if item.provider_id == "gemini")
    assert openai.model == "gpt-4.1"
    assert openai.readiness_issues == ()
    assert gemini.readiness_issues[0].code == "provider.missing_api_key"
    assert "secret-value" not in repr(snapshot)
    option = next(item for item in snapshot.options if item.provider_id == "openai")
    assert option.credential_hint == "••••alue"


def test_provider_snapshot_rejects_unknown_dotenv_provider() -> None:
    from ClipAI.core.errors import ConfigError

    with pytest.raises(ConfigError, match="CLIPAI_PROVIDER"):
        _build_provider_snapshot(load_config_bundle(), {"CLIPAI_PROVIDER": "unknown"})


def test_provider_snapshot_builds_keyless_local_gateway() -> None:
    snapshot = _build_provider_snapshot(
        load_config_bundle(),
        {
            "CLIPAI_PROVIDER": "gateway",
            "CLIPAI_GATEWAY_NAME": "Local AI",
            "CLIPAI_GATEWAY_BASE_URL": "http://localhost:8000",
            "CLIPAI_GATEWAY_MODEL": "local-model",
        },
    )
    binding = next(item for item in snapshot.bindings if item.provider_id == "gateway")
    assert snapshot.active_provider == "gateway"
    assert snapshot.connection_base_url == "http://localhost:8000/v1"
    assert binding.readiness_issues == ()


def test_configured_custom_provider_does_not_connect_during_startup() -> None:
    class NoNetworkTransport:
        def __getattr__(self, name):
            raise AssertionError(f"startup must not access transport.{name}")

    snapshot = build_provider_snapshot(
        load_config_bundle(),
        {
            "CLIPAI_PROVIDER": "gateway",
            "CLIPAI_GATEWAY_BASE_URL": "http://localhost:8000",
            "CLIPAI_GATEWAY_MODEL": "local-model",
        },
        NoNetworkTransport(),
    )

    assert snapshot.active_provider == "gateway"
    assert snapshot.bindings[-1].readiness_issues == ()


def test_missing_provider_key_is_a_first_run_settings_condition() -> None:
    snapshot = _build_provider_snapshot(load_config_bundle(), {"CLIPAI_PROVIDER": "gemini"})
    binding = next(item for item in snapshot.bindings if item.provider_id == snapshot.active_provider)

    assert _needs_provider_setup(binding.readiness_issues)


def test_unconfigured_custom_provider_is_a_nonfatal_first_run_settings_condition() -> None:
    snapshot = _build_provider_snapshot(load_config_bundle(), {"CLIPAI_PROVIDER": "gateway"})
    binding = next(item for item in snapshot.bindings if item.provider_id == snapshot.active_provider)

    assert binding.readiness_issues[0].code == "provider.gateway_not_configured"
    assert _needs_provider_setup(binding.readiness_issues)
