from __future__ import annotations

from collections.abc import Callable, Mapping

from ClipAI.app.config_schema import ConfigBundle
from ClipAI.core.errors import ConfigError
from ClipAI.core.models import EnvironmentSetting, ModelCatalogConnection, ProviderCapabilities, ProviderOption, ProviderSettingsInput, ReadinessIssue
from ClipAI.platform.dotenv_preferences import DotenvModelPreferenceStore
from ClipAI.providers.anthropic import AnthropicProvider
from ClipAI.providers.fake import FakeProvider
from ClipAI.providers.gateway import OpenAICompatibleGatewayProvider, normalize_gateway_base_url
from ClipAI.providers.gemini import GeminiProvider
from ClipAI.providers.http_transport import HttpTransport
from ClipAI.providers.model_catalog import ProviderModelCatalogClient
from ClipAI.providers.openai import OpenAIProvider
from ClipAI.providers.settings import GatewaySettings, ProviderCredential
from ClipAI.services.provider_binding import ProviderExecutionBinding, ProviderRuntimeSnapshot


class AppProviderConfigurationBackend:
    """Composition adapter for provider construction, environment mapping, and persistence."""

    def __init__(
        self,
        bundle: ConfigBundle,
        settings_store: DotenvModelPreferenceStore,
        environment_reader: Callable[[], dict[str, str]],
        transport: HttpTransport,
        model_catalog: ProviderModelCatalogClient | None = None,
    ) -> None:
        self._bundle = bundle
        self._store = settings_store
        self._environment_reader = environment_reader
        self._transport = transport
        self._catalog = model_catalog or ProviderModelCatalogClient(transport)

    def reload(self) -> ProviderRuntimeSnapshot:
        return build_provider_snapshot(self._bundle, self._environment(), self._transport)

    def persist_provider(self, provider: str) -> ProviderRuntimeSnapshot:
        self._store.save_settings((EnvironmentSetting("CLIPAI_PROVIDER", provider),))
        return self.reload()

    def persist_model(self, provider: str, model: str) -> ProviderRuntimeSnapshot:
        self._store.save_settings((EnvironmentSetting(_model_env_name(provider), model),))
        return self.reload()

    async def validate_save_and_build(self, settings: ProviderSettingsInput) -> ProviderRuntimeSnapshot:
        environment = self._environment()
        provider_settings = getattr(self._bundle.providers, settings.provider)
        effective_key = settings.api_key.strip() or environment.get(provider_settings.api_key_env, "")
        validation_settings = (
            GatewaySettings(
                settings.connection_name or "Custom Gateway",
                normalize_gateway_base_url(settings.connection_base_url),
                settings.model,
                self._bundle.providers.gateway.timeout_sec,
                available_models=(settings.model,),
            )
            if settings.provider == "gateway"
            else provider_settings
        )
        await self._catalog.list_models(settings.provider, validation_settings, effective_key)

        candidate_environment = {
            **environment,
            "CLIPAI_PROVIDER": settings.provider,
            _model_env_name(settings.provider): settings.model,
        }
        if settings.api_key.strip():
            candidate_environment[provider_settings.api_key_env] = settings.api_key.strip()
        updates = [EnvironmentSetting("CLIPAI_PROVIDER", settings.provider)]
        if settings.provider == "gateway":
            candidate_environment.update({
                "CLIPAI_GATEWAY_NAME": settings.connection_name,
                "CLIPAI_GATEWAY_BASE_URL": settings.connection_base_url,
                "CLIPAI_GATEWAY_MODEL": settings.model,
            })
            updates.extend((
                EnvironmentSetting("CLIPAI_GATEWAY_NAME", settings.connection_name.strip()),
                EnvironmentSetting("CLIPAI_GATEWAY_BASE_URL", settings.connection_base_url.strip()),
            ))
            if settings.api_key.strip():
                candidate_environment["CLIPAI_GATEWAY_API_KEY"] = settings.api_key.strip()
                updates.append(EnvironmentSetting("CLIPAI_GATEWAY_API_KEY", settings.api_key.strip()))
            updates.append(EnvironmentSetting("CLIPAI_GATEWAY_MODEL", settings.model.strip()))
        else:
            if settings.api_key.strip():
                updates.append(EnvironmentSetting(provider_settings.api_key_env, settings.api_key.strip()))
            updates.append(EnvironmentSetting(_model_env_name(settings.provider), settings.model.strip()))
        candidate = build_provider_snapshot(self._bundle, candidate_environment, self._transport)
        self._store.save_settings(tuple(updates))
        return candidate

    async def discover_models(self, provider: str, connection: ModelCatalogConnection | None) -> tuple[str, ...]:
        if provider == "anthropic":
            return self._bundle.providers.anthropic.available_models
        environment = self._environment()
        snapshot = build_provider_snapshot(self._bundle, environment, self._transport)
        option = next(item for item in snapshot.options if item.provider_id == provider)
        if provider == "gateway":
            base_url = connection.base_url if connection is not None else snapshot.connection_base_url
            fallback_model = connection.fallback_model if connection is not None else option.selected_model
            provider_settings = GatewaySettings(
                snapshot.connection_name,
                base_url,
                fallback_model,
                self._bundle.providers.gateway.timeout_sec,
                available_models=option.available_models,
            )
            api_key = (
                connection.api_key.strip() or environment.get("CLIPAI_GATEWAY_API_KEY", "")
                if connection is not None
                else environment.get("CLIPAI_GATEWAY_API_KEY", "")
            )
        else:
            provider_settings = getattr(self._bundle.providers, provider)
            api_key = environment.get(provider_settings.api_key_env, "")
        return await self._catalog.list_models(provider, provider_settings, api_key)

    def _environment(self) -> dict[str, str]:
        return {**self._environment_reader(), **self._store.read_settings()}


def build_provider_snapshot(
    bundle: ConfigBundle,
    environment: Mapping[str, str],
    transport: HttpTransport,
) -> ProviderRuntimeSnapshot:
    values = environment
    active = (values.get("CLIPAI_PROVIDER") or bundle.providers.active).strip().lower()
    allowed = ("gemini", "openai", "anthropic", "gateway")
    if active == "fake":
        binding = ProviderExecutionBinding(FakeProvider(), "fake", "fake-model")
        option = ProviderOption("fake", "Fake", ("fake-model",), "fake-model", True)
        return ProviderRuntimeSnapshot("fake", (binding,), (option,))
    if active not in allowed:
        raise ConfigError(f"CLIPAI_PROVIDER must be one of: {', '.join(allowed)}")
    bindings: list[ProviderExecutionBinding] = []
    options: list[ProviderOption] = []
    display_names = {"gemini": "Gemini", "openai": "OpenAI", "anthropic": "Anthropic"}
    provider_types = {"gemini": GeminiProvider, "openai": OpenAIProvider, "anthropic": AnthropicProvider}
    for provider_id in ("gemini", "openai", "anthropic"):
        settings = getattr(bundle.providers, provider_id)
        credential = ProviderCredential(settings.api_key_env, values.get(settings.api_key_env))
        model = (values.get(f"{provider_id.upper()}_MODEL") or settings.model).strip()
        available_models = settings.available_models or (settings.model,)
        custom_models: tuple[str, ...] = ()
        if model not in available_models:
            available_models = (model, *available_models)
            custom_models = (model,)
        issues = () if credential.value else (
            ReadinessIssue(
                "provider.missing_api_key",
                f"Set {settings.api_key_env} and reload ClipAI to use {provider_id}.",
                "llm",
            ),
        )
        provider = provider_types[provider_id](settings, credential, transport)
        bindings.append(ProviderExecutionBinding(provider, provider_id, model, issues))
        options.append(ProviderOption(
            provider_id,
            display_names[provider_id],
            available_models,
            model,
            not issues,
            custom_models,
            _credential_hint(credential.value),
        ))
    gateway_defaults = bundle.providers.gateway
    gateway_name = (values.get("CLIPAI_GATEWAY_NAME") or gateway_defaults.name or "Custom Gateway").strip()
    gateway_base_url = (values.get("CLIPAI_GATEWAY_BASE_URL") or gateway_defaults.base_url).strip()
    gateway_model = (values.get("CLIPAI_GATEWAY_MODEL") or gateway_defaults.model).strip()
    gateway_key = values.get("CLIPAI_GATEWAY_API_KEY") or ""
    gateway_ready = bool(gateway_base_url and gateway_model)
    if gateway_ready:
        gateway_base_url = normalize_gateway_base_url(gateway_base_url)
    gateway_settings = GatewaySettings(
        gateway_name or "Custom Gateway",
        gateway_base_url,
        gateway_model,
        gateway_defaults.timeout_sec,
        available_models=(gateway_model,) if gateway_model else (),
    )
    gateway_issues = () if gateway_ready else (
        ReadinessIssue(
            "provider.gateway_not_configured",
            "Configure the Custom provider URL and model before using it.",
            "llm",
        ),
    )
    bindings.append(ProviderExecutionBinding(
        OpenAICompatibleGatewayProvider(
            gateway_settings,
            ProviderCredential("CLIPAI_GATEWAY_API_KEY", gateway_key),
            transport,
        ),
        "gateway",
        gateway_model,
        gateway_issues,
    ))
    capabilities = ProviderCapabilities(True, True, True, True)
    options.append(ProviderOption(
        "gateway",
        gateway_name or "Custom Gateway",
        (gateway_model,) if gateway_model else (),
        gateway_model,
        gateway_ready,
        (gateway_model,) if gateway_model else (),
        _credential_hint(gateway_key),
        capabilities,
    ))
    return ProviderRuntimeSnapshot(active, tuple(bindings), tuple(options), gateway_name or "Custom Gateway", gateway_base_url)


def _credential_hint(value: str | None) -> str:
    secret = (value or "").strip()
    if not secret:
        return ""
    return f"••••{secret[-4:]}" if len(secret) >= 8 else "configured"


def _model_env_name(provider: str) -> str:
    return "CLIPAI_GATEWAY_MODEL" if provider == "gateway" else f"{provider.upper()}_MODEL"
