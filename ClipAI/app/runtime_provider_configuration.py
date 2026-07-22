from __future__ import annotations

from collections.abc import Callable
from typing import TypeAlias
import uuid

from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.commands import OpenProviderSettings, RefreshProviderModels, ReloadConfiguration, SelectProvider, SelectProviderModel, ValidateAndSaveProviderSettings
from ClipAI.core.ports import ModelSelectionPresenter, OperationTracker, ProviderSelectionPresenter, ProviderSettingsPresenter
from ClipAI.services.provider_configuration import ProviderConfigurationCoordinator, ProviderConfigurationResult, ProviderConfigurationUpdate


ProviderRuntimeCommand: TypeAlias = SelectProviderModel | SelectProvider | ReloadConfiguration | OpenProviderSettings | ValidateAndSaveProviderSettings | RefreshProviderModels | ProviderConfigurationResult


class ProviderConfigurationRuntimeModule:
    """Owns runtime scheduling and UI projection for provider configuration."""

    def __init__(
        self,
        *,
        coordinator: ProviderConfigurationCoordinator,
        supervisor: TaskSupervisor,
        enqueue: Callable[[object], None],
        operation_tracker: OperationTracker | None = None,
        model_selection_presenter: ModelSelectionPresenter | None = None,
        provider_selection_presenter: ProviderSelectionPresenter | None = None,
        provider_settings_presenter: ProviderSettingsPresenter | None = None,
    ) -> None:
        self._coordinator = coordinator
        self._supervisor = supervisor
        self._enqueue = enqueue
        self._operation_tracker = operation_tracker
        self._model_selection_presenter = model_selection_presenter
        self._provider_selection_presenter = provider_selection_presenter
        self._provider_settings_presenter = provider_settings_presenter

    @property
    def coordinator(self) -> ProviderConfigurationCoordinator:
        return self._coordinator

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
        elif isinstance(command, ValidateAndSaveProviderSettings):
            self._save(command)
        elif isinstance(command, RefreshProviderModels):
            self._refresh(command)
        elif isinstance(command, ProviderConfigurationResult):
            self._project(self._coordinator.complete(command))

    def _save(self, command: ValidateAndSaveProviderSettings) -> None:
        operation_id = command.operation_id or uuid.uuid4().hex
        work, update = self._coordinator.begin_save(command.settings, operation_id)
        self._project(update)
        if work is None:
            return
        self._supervisor.submit(
            f"provider-settings:{operation_id}",
            lambda: self._enqueue(self._coordinator.execute(work)),
            lambda error: self._enqueue(ProviderConfigurationResult(
                "save", operation_id, command.settings.provider,
                error="Provider validation failed unexpectedly. Try again.",
            )),
        )

    def _refresh(self, command: RefreshProviderModels) -> None:
        provider = command.provider or self._coordinator.active_binding.provider_id
        operation_id = command.operation_id or uuid.uuid4().hex
        work, update = self._coordinator.begin_refresh(provider, operation_id, command.connection)
        self._project(update)
        if work is None:
            return
        self._supervisor.submit(
            f"provider-models:{operation_id}",
            lambda: self._enqueue(self._coordinator.execute(work)),
            lambda error: self._enqueue(ProviderConfigurationResult(
                "refresh", operation_id, provider,
                error="The provider returned no usable models. The previous catalog remains active.",
            )),
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
