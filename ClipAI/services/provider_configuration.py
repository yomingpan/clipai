from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from ClipAI.core.errors import ConfigError, ProviderAuthError, ProviderResponseError, ProviderTimeoutError, ProviderUnavailableError
from ClipAI.core.models import (
    ModelCatalogConnection,
    ModelSelectionState,
    ProviderOption,
    ProviderSelectionState,
    ProviderSettingsInput,
    ProviderSettingsOperationKind,
    ProviderSettingsState,
    UserFacingError,
)
from ClipAI.services.provider_binding import ProviderExecutionBinding, ProviderRuntimeSnapshot


class ProviderConfigurationBackend(Protocol):
    def reload(self) -> ProviderRuntimeSnapshot: ...

    def persist_provider(self, provider: str) -> ProviderRuntimeSnapshot: ...

    def persist_model(self, provider: str, model: str) -> ProviderRuntimeSnapshot: ...

    def validate_save_and_build(self, settings: ProviderSettingsInput) -> ProviderRuntimeSnapshot: ...

    def discover_models(self, provider: str, connection: ModelCatalogConnection | None) -> tuple[str, ...]: ...


@dataclass(frozen=True)
class ProviderConfigurationWork:
    kind: ProviderSettingsOperationKind
    operation_id: str
    provider: str
    settings: ProviderSettingsInput | None = None
    connection: ModelCatalogConnection | None = None


@dataclass(frozen=True)
class ProviderConfigurationResult:
    kind: ProviderSettingsOperationKind
    operation_id: str
    provider: str
    snapshot: ProviderRuntimeSnapshot | None = None
    models: tuple[str, ...] = ()
    error: str = ""


@dataclass(frozen=True)
class ProviderConfigurationUpdate:
    settings_state: ProviderSettingsState | None = None
    error: UserFacingError | None = None
    ignored: bool = False
    show_settings: bool = False


@dataclass(frozen=True)
class _ActiveOperation:
    kind: ProviderSettingsOperationKind
    operation_id: str
    provider: str


class ProviderConfigurationCoordinator:
    """Single owner of provider configuration state and operation identity."""

    def __init__(self, snapshot: ProviderRuntimeSnapshot, backend: ProviderConfigurationBackend) -> None:
        self._backend = backend
        self._snapshot = snapshot
        self._settings_target = snapshot.active_provider
        self._operation: _ActiveOperation | None = None

    @property
    def active_binding(self) -> ProviderExecutionBinding:
        return self._binding(self._snapshot.active_provider)

    @property
    def busy(self) -> bool:
        return self._operation is not None

    def model_selection(self) -> ModelSelectionState:
        option = self._option(self._snapshot.active_provider)
        operation = self._operation
        return ModelSelectionState(
            option.provider_id,
            option.available_models,
            option.selected_model,
            refreshing=bool(operation and operation.kind == "refresh" and operation.provider == option.provider_id),
            custom_models=option.custom_models,
            configuration_pending=operation is not None,
        )

    def provider_selection(self, *, reloading: bool = False) -> ProviderSelectionState:
        return ProviderSelectionState(
            self._snapshot.options,
            self._snapshot.active_provider,
            reloading=reloading,
            configuration_pending=self._operation is not None,
        )

    def settings_state(
        self,
        provider: str | None = None,
        *,
        operation_state: Literal["idle", "pending", "succeeded", "failed"] = "idle",
        operation_kind: ProviderSettingsOperationKind | None = None,
        message: str = "",
        operation_id: str = "",
    ) -> ProviderSettingsState:
        selected = provider or self._settings_target
        if not any(option.provider_id == selected for option in self._snapshot.options):
            selected = self._snapshot.active_provider
        self._settings_target = selected
        option = self._option(selected)
        return ProviderSettingsState(
            self._snapshot.options,
            selected,
            option.selected_model,
            operation_state,
            operation_kind,
            message,
            operation_id,
            self._snapshot.connection_name,
            self._snapshot.connection_base_url,
        )

    def open_settings(self, provider: str | None = None) -> ProviderConfigurationUpdate:
        if self.busy:
            return self._busy_update(provider)
        try:
            self._accept_snapshot(self._backend.reload())
        except Exception:
            return ProviderConfigurationUpdate(
                self.settings_state(provider, operation_state="failed", message="Could not reload saved provider settings. Check .env and try again.")
            )
        return ProviderConfigurationUpdate(self.settings_state(provider), show_settings=True)

    def reload(self) -> ProviderConfigurationUpdate:
        if self.busy:
            return self._busy_update()
        try:
            snapshot = self._backend.reload()
            active = next(item for item in snapshot.bindings if item.provider_id == snapshot.active_provider)
            if active.readiness_issues:
                raise ValueError("active provider is not configured")
            self._accept_snapshot(snapshot)
        except (ConfigError, OSError, ValueError, KeyError, StopIteration):
            return ProviderConfigurationUpdate(error=UserFacingError(
                "Could not reload provider configuration.",
                "The previous provider remains active. Check .env and try again.",
            ))
        return ProviderConfigurationUpdate()

    def select_provider(self, provider: str) -> ProviderConfigurationUpdate:
        if self.busy:
            return self._busy_update()
        try:
            self._accept_snapshot(self._backend.reload())
        except (ConfigError, OSError, ValueError, KeyError):
            return ProviderConfigurationUpdate(error=UserFacingError(
                "Provider switch rejected.", "Could not reload .env. The previous provider remains active."
            ))
        binding = next((item for item in self._snapshot.bindings if item.provider_id == provider), None)
        option = next((item for item in self._snapshot.options if item.provider_id == provider), None)
        if binding is None or option is None or binding.readiness_issues:
            self._settings_target = provider if option is not None else self._snapshot.active_provider
            return ProviderConfigurationUpdate(
                self.settings_state(self._settings_target),
                UserFacingError("Provider switch rejected.", "Configure this provider's API key and try again."),
                show_settings=True,
            )
        if provider == self._snapshot.active_provider:
            return ProviderConfigurationUpdate()
        try:
            self._accept_snapshot(self._backend.persist_provider(provider))
        except OSError:
            return ProviderConfigurationUpdate(error=UserFacingError(
                "Could not save the provider selection.",
                "The previous provider remains active. Check .env permissions and try again.",
            ))
        return ProviderConfigurationUpdate()

    def select_model(self, provider: str, model: str) -> ProviderConfigurationUpdate:
        if self.busy:
            return self._busy_update()
        option = next((item for item in self._snapshot.options if item.provider_id == provider), None)
        if provider != self._snapshot.active_provider or option is None or model not in option.available_models:
            return ProviderConfigurationUpdate(error=UserFacingError(
                "Model switch rejected.", "Choose a model listed for the active provider."
            ))
        if model == option.selected_model:
            return ProviderConfigurationUpdate()
        try:
            self._accept_snapshot(self._backend.persist_model(provider, model))
        except OSError:
            return ProviderConfigurationUpdate(error=UserFacingError(
                "Could not save the model selection.",
                "The previous model remains active. Check .env permissions and try again.",
            ))
        return ProviderConfigurationUpdate()

    def begin_save(self, settings: ProviderSettingsInput, operation_id: str) -> tuple[ProviderConfigurationWork | None, ProviderConfigurationUpdate]:
        if self.busy:
            return None, self._busy_update(settings.provider)
        try:
            self._accept_snapshot(self._backend.reload())
        except (ConfigError, OSError, ValueError, KeyError):
            return None, ProviderConfigurationUpdate(self.settings_state(
                settings.provider,
                operation_state="failed",
                operation_kind="save",
                message="Could not reload saved provider settings. Check .env and try again.",
            ))
        option = next((item for item in self._snapshot.options if item.provider_id == settings.provider), None)
        capabilities = option.capabilities if option is not None else None
        model_allowed = bool(settings.model.strip()) if capabilities and capabilities.editable_model else bool(option and settings.model in option.available_models)
        key_present = bool(settings.api_key.strip()) or bool(option and (option.configured or option.capabilities.credential_optional))
        connection_valid = not (capabilities and capabilities.custom_endpoint) or bool(settings.connection_name.strip() and settings.connection_base_url.strip())
        if option is None or not model_allowed or not key_present or not connection_valid:
            return None, ProviderConfigurationUpdate(self.settings_state(
                settings.provider,
                operation_state="failed",
                operation_kind="save",
                message="Provider, model, and API key are required.",
            ))
        active = _ActiveOperation("save", operation_id, settings.provider)
        self._operation = active
        work = ProviderConfigurationWork("save", operation_id, settings.provider, settings=settings)
        return work, ProviderConfigurationUpdate(self.settings_state(
            settings.provider,
            operation_state="pending",
            operation_kind="save",
            message=_validation_message(settings.api_key, option),
            operation_id=operation_id,
        ))

    def begin_refresh(
        self,
        provider: str,
        operation_id: str,
        connection: ModelCatalogConnection | None,
    ) -> tuple[ProviderConfigurationWork | None, ProviderConfigurationUpdate]:
        if self.busy:
            return None, self._busy_update(provider)
        try:
            self._accept_snapshot(self._backend.reload())
        except (ConfigError, OSError, ValueError, KeyError):
            return None, ProviderConfigurationUpdate(self.settings_state(
                provider,
                operation_state="failed",
                operation_kind="refresh",
                message="Could not reload saved provider settings. Check .env and try again.",
            ))
        if not any(option.provider_id == provider for option in self._snapshot.options):
            return None, ProviderConfigurationUpdate()
        self._operation = _ActiveOperation("refresh", operation_id, provider)
        work = ProviderConfigurationWork("refresh", operation_id, provider, connection=connection)
        return work, ProviderConfigurationUpdate(self.settings_state(
            provider,
            operation_state="pending",
            operation_kind="refresh",
            message="Refreshing model catalog...",
            operation_id=operation_id,
        ))

    def execute(self, work: ProviderConfigurationWork) -> ProviderConfigurationResult:
        try:
            if work.kind == "save":
                assert work.settings is not None
                snapshot = self._backend.validate_save_and_build(work.settings)
                return ProviderConfigurationResult(work.kind, work.operation_id, work.provider, snapshot=snapshot)
            models = tuple(dict.fromkeys(model.strip() for model in self._backend.discover_models(work.provider, work.connection) if model.strip()))
            if not models:
                raise ValueError("provider returned no models")
            return ProviderConfigurationResult(work.kind, work.operation_id, work.provider, models=models)
        except Exception as exc:
            message = _safe_error(exc)
            if work.kind == "refresh" and message == "Provider validation failed unexpectedly. Try again.":
                message = "The provider returned no usable models. The previous catalog remains active."
            return ProviderConfigurationResult(work.kind, work.operation_id, work.provider, error=message)

    def complete(self, result: ProviderConfigurationResult) -> ProviderConfigurationUpdate:
        operation = self._operation
        if operation is None or (operation.kind, operation.operation_id, operation.provider) != (result.kind, result.operation_id, result.provider):
            return ProviderConfigurationUpdate(ignored=True)
        self._operation = None
        if result.error:
            title = "Provider settings were not saved." if result.kind == "save" else "Could not refresh models."
            return ProviderConfigurationUpdate(
                self.settings_state(result.provider, operation_state="failed", operation_kind=result.kind, message=result.error),
                UserFacingError(title, result.error),
            )
        if result.kind == "save":
            assert result.snapshot is not None
            self._accept_snapshot(result.snapshot)
            return ProviderConfigurationUpdate(self.settings_state(
                result.provider,
                operation_state="succeeded",
                operation_kind="save",
                message="Provider settings saved.",
            ))
        self._replace_catalog(result.provider, result.models)
        return ProviderConfigurationUpdate(self.settings_state(
            result.provider,
            operation_state="succeeded",
            operation_kind="refresh",
            message="Model catalog refreshed.",
        ))

    def _busy_update(self, provider: str | None = None) -> ProviderConfigurationUpdate:
        operation = self._operation
        assert operation is not None
        return ProviderConfigurationUpdate(
            self.settings_state(
                provider or operation.provider,
                operation_state="pending",
                operation_kind=operation.kind,
                message="Provider configuration is already in progress.",
                operation_id=operation.operation_id,
            ),
            UserFacingError("Provider configuration is busy.", "Wait for the current provider operation to finish."),
        )

    def _accept_snapshot(self, snapshot: ProviderRuntimeSnapshot) -> None:
        previous = {item.provider_id: item for item in self._snapshot.options}
        merged: list[ProviderOption] = []
        for fresh in snapshot.options:
            old = previous.get(fresh.provider_id)
            models = old.available_models if old is not None and old.available_models else fresh.available_models
            selected = fresh.selected_model
            custom = old.custom_models if old is not None else fresh.custom_models
            if selected and selected not in models:
                models = (selected, *models)
                custom = tuple(dict.fromkeys((selected, *custom)))
            merged.append(ProviderOption(
                fresh.provider_id,
                fresh.display_name,
                models,
                selected,
                fresh.configured,
                custom,
                fresh.credential_hint,
                fresh.capabilities,
            ))
        self._snapshot = ProviderRuntimeSnapshot(
            snapshot.active_provider,
            snapshot.bindings,
            tuple(merged),
            snapshot.connection_name,
            snapshot.connection_base_url,
        )

    def _replace_catalog(self, provider: str, catalog: tuple[str, ...]) -> None:
        option = self._option(provider)
        keep_current = bool(option.selected_model) and option.selected_model not in catalog
        models = (option.selected_model, *catalog) if keep_current else catalog
        custom = (option.selected_model,) if keep_current else ()
        updated = ProviderOption(
            option.provider_id,
            option.display_name,
            models,
            option.selected_model,
            option.configured,
            custom,
            option.credential_hint,
            option.capabilities,
        )
        self._snapshot = ProviderRuntimeSnapshot(
            self._snapshot.active_provider,
            self._snapshot.bindings,
            tuple(updated if item.provider_id == provider else item for item in self._snapshot.options),
            self._snapshot.connection_name,
            self._snapshot.connection_base_url,
        )

    def _binding(self, provider: str) -> ProviderExecutionBinding:
        return next(item for item in self._snapshot.bindings if item.provider_id == provider)

    def _option(self, provider: str) -> ProviderOption:
        return next(item for item in self._snapshot.options if item.provider_id == provider)


def _safe_error(error: Exception) -> str:
    if isinstance(error, ProviderAuthError):
        return "The provider rejected this API key. Check the key and try again."
    if isinstance(error, ProviderTimeoutError):
        return "Provider validation timed out. Try again."
    if isinstance(error, ProviderUnavailableError):
        return "Could not connect to the provider. Check the network and try again."
    if isinstance(error, (ProviderResponseError, ConfigError)):
        return str(error)
    if isinstance(error, OSError):
        return "Could not write .env. Check file permissions and try again."
    return "Provider validation failed unexpectedly. Try again."


def _validation_message(api_key: str, option: ProviderOption) -> str:
    if api_key.strip():
        return "Validating the new API key..."
    if option.credential_hint == "configured":
        return "Validating with the saved API key..."
    if option.credential_hint:
        return f"Validating with the saved API key ending in {option.credential_hint[-4:]}..."
    return "Validating provider without an API key..."
