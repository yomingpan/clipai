from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from ClipAI.core.models import ActionFeedbackRecord, ActiveWorkflowContext, ApplicationStatus, ClipboardSnapshot, DisplayMetrics, EnvironmentSetting, GuidancePreferences, ImageContent, LLMRequest, LLMResult, ModelSelectionState, OperationKind, OutputOperationResult, ProviderSelectionState, ProviderSettingsState, SpeechRequest, UserFacingError
from ClipAI.core.state import CancellationToken, SessionSnapshot


class LLMProvider(Protocol):
    def complete(self, request: LLMRequest, cancellation: CancellationToken) -> LLMResult: ...


class ClipboardReader(Protocol):
    def read_text(self) -> str: ...

    def read_image(self) -> ImageContent | None: ...


class ClipboardWriter(Protocol):
    def write_text(self, text: str) -> None: ...


class ClipboardStore(ClipboardReader, ClipboardWriter, Protocol):
    pass


class ClipboardTransactionStore(ClipboardStore, Protocol):
    def snapshot(self) -> ClipboardSnapshot: ...

    def sequence_number(self) -> int: ...

    def restore_if_unchanged(self, snapshot: ClipboardSnapshot, expected_sequence: int) -> bool: ...


class SelectionReader(Protocol):
    def read_text(self) -> str: ...


class ResultPresenter(Protocol):
    def render(self, snapshot: SessionSnapshot) -> None: ...


class ApplicationView(ResultPresenter, Protocol):
    def set_command_sink(self, sink: Callable[[object], None]) -> None: ...

    def run(self, command_pump: Callable[[], None]) -> None: ...

    def stop(self) -> None: ...



class OutputOperationPresenter(Protocol):
    def present_output_operation(self, result: OutputOperationResult) -> None: ...


class WorkflowContextReader(Protocol):
    def workflow_context(self, workflow_id: str) -> ActiveWorkflowContext | None: ...


class ArchiveStore(Protocol):
    def save(self, text: str) -> None: ...


class ActionFeedbackStore(Protocol):
    def append(self, record: ActionFeedbackRecord) -> None: ...


class GuidancePreferencesStore(Protocol):
    def load(self) -> GuidancePreferences: ...

    def save(self, preferences: GuidancePreferences) -> None: ...


class SpeechOutput(Protocol):
    def speak(self, request: SpeechRequest) -> None: ...

    def stop(self) -> None: ...


class KeyboardOutput(Protocol):
    def paste(self) -> None: ...


class StatusIndicator(Protocol):
    def set_status(self, status: ApplicationStatus) -> None: ...

    def set_memory_active(self, active: bool) -> None: ...


class ModelSelectionPresenter(Protocol):
    def set_model_selection(self, selection: ModelSelectionState) -> None: ...


class ProviderSelectionPresenter(Protocol):
    def set_provider_selection(self, selection: ProviderSelectionState) -> None: ...


class ProviderSettingsPresenter(Protocol):
    def show_provider_settings(self, state: ProviderSettingsState) -> None: ...

    def set_provider_settings(self, state: ProviderSettingsState) -> None: ...


class GuidancePreferencesPresenter(Protocol):
    def set_guidance_preferences(self, preferences: GuidancePreferences) -> None: ...


class ModelPreferenceStore(Protocol):
    def save_model(self, env_name: str, model: str) -> None: ...


class EnvironmentSettingsStore(Protocol):
    def save_settings(self, settings: tuple[EnvironmentSetting, ...]) -> None: ...


class OperationHandle(Protocol):
    def succeed(self) -> None: ...

    def fail(self) -> None: ...

    def cancel(self) -> None: ...


class OperationTracker(Protocol):
    def start(self, operation_id: str, kind: OperationKind) -> OperationHandle: ...

    def report_waiting(self) -> None: ...

    def report_error(self, message: str, suggestion: str = "") -> None: ...

    @property
    def last_error(self) -> UserFacingError | None: ...

    def stop(self) -> None: ...


class UserNotifier(Protocol):
    def notify(self, title: str, message: str) -> None: ...


class DiagnosticsExporter(Protocol):
    def export(self) -> Path: ...


class DisplayMetricsReader(Protocol):
    def current(self) -> DisplayMetrics: ...


class Stoppable(Protocol):
    def stop(self) -> None: ...


class RuntimeComponent(Stoppable, Protocol):
    def start(self) -> None: ...
