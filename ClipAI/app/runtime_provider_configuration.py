from __future__ import annotations

from collections.abc import Callable
from typing import TypeAlias
import uuid

from ClipAI.app.provider_execution import ProviderExecutionModule
from ClipAI.core.commands import CloseProviderSettings, OpenProviderSettings, RefreshProviderModels, ReloadConfiguration, SelectProvider, SelectProviderModel, ValidateAndSaveProviderSettings
from ClipAI.core.models import InterruptibleOperationRef
from ClipAI.core.ports import ModelSelectionPresenter, OperationTracker, ProviderSelectionPresenter, ProviderSettingsPresenter
from ClipAI.services.provider_configuration import ProviderConfigurationCoordinator, ProviderConfigurationResult, ProviderConfigurationUpdate
from ClipAI.services.user_control import InterruptibleOperationLease, UserControlCoordinator


ProviderRuntimeCommand: TypeAlias = SelectProviderModel | SelectProvider | ReloadConfiguration | OpenProviderSettings | CloseProviderSettings | ValidateAndSaveProviderSettings | RefreshProviderModels | ProviderConfigurationResult


class ProviderConfigurationRuntimeModule:
    """Owns runtime scheduling and UI projection for provider configuration."""

    def __init__(
        self,
        *,
        coordinator: ProviderConfigurationCoordinator,
        provider_execution: ProviderExecutionModule,
        enqueue: Callable[[object], None],
        operation_tracker: OperationTracker | None = None,
        model_selection_presenter: ModelSelectionPresenter | None = None,
        provider_selection_presenter: ProviderSelectionPresenter | None = None,
        provider_settings_presenter: ProviderSettingsPresenter | None = None,
        user_control: UserControlCoordinator | None = None,
    ) -> None:
        self._coordinator = coordinator
        self._provider_execution = provider_execution
        self._enqueue = enqueue
        self._operation_tracker = operation_tracker
        self._model_selection_presenter = model_selection_presenter
        self._provider_selection_presenter = provider_selection_presenter
        self._provider_settings_presenter = provider_settings_presenter
        self._user_control = user_control
        self._leases: dict[str, InterruptibleOperationLease] = {}

    @property
    def coordinator(self) -> ProviderConfigurationCoordinator:
        return self._coordinator

    def bind_user_control(self, user_control: UserControlCoordinator) -> None:
        self._user_control = user_control

    def handle(self, command: ProviderRuntimeCommand) -> None:
        if isinstance(command, SelectProviderModel):
            self._project(self._coordinator.select_model(command.provider, command.model))
        elif isinstance(command, SelectProvider):
            self._project(self._coordinator.select_provider(command.provider))
        elif isinstance(command, ReloadConfiguration):
            if self._provider_selection_presenter is not None:
                self._provider_selection_presenter.set_provider_selection(self._coordinator.provider_selection(reloading=True))
            self._project(self._coordinator.reload())
        elif isinstance(command, OpenProviderSettings):
            if self._provider_settings_presenter is not None:
                self._project(self._coordinator.open_settings(command.provider))
        elif isinstance(command, CloseProviderSettings):
            self._close_settings()
        elif isinstance(command, ValidateAndSaveProviderSettings):
            self._save(command)
        elif isinstance(command, RefreshProviderModels):
            self._refresh(command)
        elif isinstance(command, ProviderConfigurationResult):
            lease = self._leases.pop(command.operation_id, None)
            if lease is not None:
                lease.finish()
            self._project(self._coordinator.complete(command))

    def _close_settings(self) -> None:
        active = self._coordinator.active_operation
        if active is not None:
            kind, operation_id = active
            self._project(self._coordinator.cancel_active())
            self._provider_execution.cancel(
                f"provider-settings:{operation_id}" if kind == "save" else f"provider-models:{operation_id}"
            )
            lease = self._leases.pop(operation_id, None)
            if lease is not None:
                lease.finish()
        if self._provider_settings_presenter is not None:
            self._provider_settings_presenter.close_provider_settings()

    def _save(self, command: ValidateAndSaveProviderSettings) -> None:
        operation_id = command.operation_id or uuid.uuid4().hex
        work, update = self._coordinator.begin_save(command.settings, operation_id)
        self._project(update)
        if work is None:
            return
        if self._user_control is not None:
            self._leases[operation_id] = self._user_control.begin(InterruptibleOperationRef(
                operation_id,
                "provider_configuration",
                surface_id="provider-settings",
            ))
        self._provider_execution.start(
            f"provider-settings:{operation_id}",
            lambda: self._coordinator.execute(work),
            self._enqueue,
            lambda error: self._enqueue(ProviderConfigurationResult(
                "save", operation_id, command.settings.provider,
                error="Provider validation failed unexpectedly. Try again.",
            )),
            lambda: None,
        )

    def _refresh(self, command: RefreshProviderModels) -> None:
        provider = command.provider or self._coordinator.active_binding.provider_id
        operation_id = command.operation_id or uuid.uuid4().hex
        work, update = self._coordinator.begin_refresh(provider, operation_id, command.connection)
        self._project(update)
        if work is None:
            return
        if self._user_control is not None:
            self._leases[operation_id] = self._user_control.begin(InterruptibleOperationRef(
                operation_id,
                "provider_configuration",
                surface_id="provider-settings",
            ))
        self._provider_execution.start(
            f"provider-models:{operation_id}",
            lambda: self._coordinator.execute(work),
            self._enqueue,
            lambda error: self._enqueue(ProviderConfigurationResult(
                "refresh", operation_id, provider,
                error="The provider returned no usable models. The previous catalog remains active.",
            )),
            lambda: None,
        )

    def _project(self, update: ProviderConfigurationUpdate) -> None:
        if update.ignored:
            return
        if self._provider_selection_presenter is not None:
            self._provider_selection_presenter.set_provider_selection(self._coordinator.provider_selection())
        if self._model_selection_presenter is not None:
            self._model_selection_presenter.set_model_selection(self._coordinator.model_selection())
        if self._provider_settings_presenter is not None and update.settings_state is not None:
            if update.show_settings:
                self._provider_settings_presenter.show_provider_settings(update.settings_state)
            else:
                self._provider_settings_presenter.set_provider_settings(update.settings_state)
        if update.error is not None and self._operation_tracker is not None:
            self._operation_tracker.report_error(update.error.message, update.error.suggestion)
