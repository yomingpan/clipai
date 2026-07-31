import asyncio
import pytest

from ClipAI.app.config_loader import load_config_bundle
from ClipAI.app.provider_configuration import AppProviderConfigurationBackend
from ClipAI.core.models import ProviderSettingsInput


class Store:
    def __init__(self) -> None:
        self.saved = []
        self.values = {}

    def read_settings(self):
        return dict(self.values)

    def save_settings(self, settings):
        self.saved.append(settings)
        self.values.update((item.name, item.value) for item in settings)


class Catalog:
    def __init__(self, error=None) -> None:
        self.error = error
        self.calls = []

    async def list_models(self, provider, settings, api_key):
        self.calls.append((provider, settings, api_key))
        if self.error is not None:
            raise self.error
        return (settings.model,)


class Transport:
    pass


def test_backend_validates_before_persisting_provider_settings() -> None:
    store = Store()
    catalog = Catalog(RuntimeError("validation failed"))
    backend = AppProviderConfigurationBackend(load_config_bundle(), store, lambda: {}, Transport(), catalog)

    with pytest.raises(RuntimeError, match="validation failed"):
        asyncio.run(backend.validate_save_and_build(ProviderSettingsInput("gemini", "gemini-2.5-flash", "secret")))

    assert store.saved == []


def test_backend_maps_generic_connection_input_to_gateway_environment() -> None:
    store = Store()
    catalog = Catalog()
    backend = AppProviderConfigurationBackend(load_config_bundle(), store, lambda: {}, Transport(), catalog)
    settings = ProviderSettingsInput(
        "gateway",
        "local-model",
        "secret",
        "Local AI",
        "http://localhost:8000",
    )

    snapshot = asyncio.run(backend.validate_save_and_build(settings))

    assert snapshot.active_provider == "gateway"
    assert snapshot.connection_name == "Local AI"
    assert snapshot.connection_base_url == "http://localhost:8000/v1"
    assert [(item.name, item.value) for item in store.saved[0]] == [
        ("CLIPAI_PROVIDER", "gateway"),
        ("CLIPAI_GATEWAY_NAME", "Local AI"),
        ("CLIPAI_GATEWAY_BASE_URL", "http://localhost:8000"),
        ("CLIPAI_GATEWAY_API_KEY", "secret"),
        ("CLIPAI_GATEWAY_MODEL", "local-model"),
    ]
    assert "secret" not in repr(settings)
