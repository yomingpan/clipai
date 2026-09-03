from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Protocol, TypeVar

from ClipAI.core.models import ActionFeedbackRecord, ActionLanguagePackSelectionRead, ActionLanguagePackSelectionState, ActiveWorkflowContext, ApplicationStatus, DisplayMetrics, EntryPanelSnapshot, EnvironmentSetting, ExternalWindowActivationOutcome, ExternalWindowRef, GuidancePreferences, ImageContent, LLMProviderEvent, LLMRequest, ModelSelectionState, ModifierHoldId, OperationKind, OutputOperationResult, PasteDispatchReceipt, PasteTarget, PersonalStyleCollection, PersonalStyleState, ProviderSelectionState, ProviderSettingsState, ShortcutGuideSnapshot, ShortcutObservationSnapshot, SpeechRequest, SpeechSpeedState, UserFacingError, UserPreferences, WorkflowAttention
from ClipAI.core.state import CancellationToken, SessionSnapshot
from ClipAI.core.voice import VoiceCaptureId, VoiceCaptureSurfaceContext, VoiceEngineEvent, VoiceLanguage, VoiceProjection, VoiceSetupId


class LLMProvider(Protocol):
    def execute(self, request: LLMRequest, cancellation: CancellationToken, *, stream: bool) -> AsyncIterator[LLMProviderEvent]: ...


class ClipboardReader(Protocol):
    def read_text(self) -> str: ...

    def read_image(self) -> ImageContent | None: ...


class ClipboardWriter(Protocol):
    def write_text(self, text: str) -> None: ...


class ClipboardStore(ClipboardReader, ClipboardWriter, Protocol):
    pass


ClipboardSnapshotT = TypeVar("ClipboardSnapshotT")


class ClipboardTransactionStore(ClipboardStore, Protocol[ClipboardSnapshotT]):
    def snapshot(self) -> ClipboardSnapshotT: ...

    def write_transient_text(self, text: str) -> None: ...

    def sequence_number(self) -> int: ...

    def restore_if_unchanged(self, snapshot: ClipboardSnapshotT, expected_sequence: int) -> bool: ...


class SelectionCaptureAdapter(Protocol):
    def modifier_is_pressed(self, modifier: str) -> bool | None: ...

    def copy_selection(self) -> None: ...


class SelectionReader(Protocol):
    def read_text(self, cancellation: CancellationToken | None = None) -> str: ...


class ResultPresenter(Protocol):
    def render(self, snapshot: SessionSnapshot) -> None: ...


class WorkflowAttentionPresenter(Protocol):
    def present_workflow_attention(self, attention: WorkflowAttention) -> None: ...


class EntryPanelPresenter(Protocol):
    def present_entry_panel(self, snapshot: EntryPanelSnapshot | None) -> None: ...

    def transition_entry_panel_to_popup(
        self,
        panel_id: str,
        workflow_id: str,
    ) -> None: ...


class ApplicationView(ResultPresenter, Protocol):
    def set_command_sink(self, sink: Callable[[object], None]) -> None: ...

    def run(self, command_pump: Callable[[], None]) -> None: ...

    def stop(self) -> None: ...

    def present_paste_target(self, target: PasteTarget | None) -> None: ...

    def show_about(self) -> None: ...

    def close_about(self) -> None: ...

    def open_github(self, url: str) -> None: ...



class OutputOperationPresenter(Protocol):
    def present_output_operation(self, result: OutputOperationResult) -> None: ...


class WorkflowContextReader(Protocol):
    def workflow_context(self, workflow_id: str) -> ActiveWorkflowContext | None: ...


class VoiceCaptureContextReader(Protocol):
    def voice_capture_surface_context(self, workflow_id: str) -> VoiceCaptureSurfaceContext | None: ...


class ArchiveStore(Protocol):
    def save(self, text: str) -> None: ...


class ActionFeedbackStore(Protocol):
    def append(self, record: ActionFeedbackRecord) -> None: ...


class ActionLanguagePackSelectionStore(Protocol):
    def load(self) -> ActionLanguagePackSelectionRead: ...

    def save(self, pack_id: str) -> None: ...


class ActionLanguagePackSelectionPresenter(Protocol):
    def set_action_language_selection(
        self,
        state: ActionLanguagePackSelectionState,
    ) -> None: ...


class UserPreferencesStore(Protocol):
    def load(self) -> UserPreferences: ...

    def save(self, preferences: UserPreferences) -> None: ...


class PersonalStyleStore(Protocol):
    def load(self) -> PersonalStyleCollection: ...

    def save(self, collection: PersonalStyleCollection) -> None: ...


class PersonalStyleFileReader(Protocol):
    def read_text(self, path: str) -> str: ...


class SpeechOutput(Protocol):
    def speak(self, request: SpeechRequest) -> None: ...

    def stop(self) -> None: ...


class TargetedPasteOutput(Protocol):
    def dispatch(
        self,
        operation_id: str,
        target: PasteTarget,
        cancellation: CancellationToken,
    ) -> PasteDispatchReceipt: ...


class ExternalWindowActivator(Protocol):
    def activate(
        self,
        target: ExternalWindowRef,
        cancellation: CancellationToken,
    ) -> ExternalWindowActivationOutcome: ...

    def confirm(
        self,
        target: ExternalWindowRef,
        cancellation: CancellationToken | None = None,
    ) -> ExternalWindowActivationOutcome: ...


class PasteTargetPresenter(Protocol):
    def present_paste_target(self, target: PasteTarget | None) -> None: ...


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

    def close_provider_settings(self) -> None: ...


class PersonalStylePresenter(Protocol):
    def show_personal_styles(self, state: PersonalStyleState) -> None: ...

    def set_personal_styles(self, state: PersonalStyleState) -> None: ...

    def close_personal_styles(self) -> None: ...


class GuidancePreferencesPresenter(Protocol):
    def set_guidance_preferences(self, preferences: GuidancePreferences) -> None: ...


class SpeechSpeedPresenter(Protocol):
    def set_speech_speed(self, state: SpeechSpeedState) -> None: ...


class ShortcutGuidePresenter(Protocol):
    def show_shortcut_guide(self, snapshot: ShortcutGuideSnapshot) -> None: ...

    def set_shortcut_guide(self, snapshot: ShortcutGuideSnapshot) -> None: ...

    def close_shortcut_guide(self) -> None: ...


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


class PointerPressReader(Protocol):
    def poll(self) -> tuple[int, int] | None: ...


class NativeWindowSurface(Protocol):
    """Native facts and operations for one toolkit-owned top-level window."""

    def hide_from_task_switcher(self, toolkit_child_id: int) -> bool: ...

    def activate(self, toolkit_child_id: int) -> bool: ...

    def show_without_activation(self, toolkit_child_id: int) -> bool: ...

    def owns_foreground(self, toolkit_child_id: int) -> bool: ...

    def install_icon(self, toolkit_child_id: int, icon_path: Path) -> tuple[int, ...]: ...

    def destroy_icons(self, handles: tuple[int, ...]) -> None: ...


class Stoppable(Protocol):
    def stop(self) -> None: ...


class ShortcutObservationLease(Protocol):
    @property
    def snapshot(self) -> ShortcutObservationSnapshot: ...

    def close(self) -> None: ...


class ShortcutInput(Stoppable, Protocol):
    def observe(self) -> ShortcutObservationLease: ...

    def settle_entry_panel_hold(self, hold_id: ModifierHoldId) -> None: ...


class RuntimeComponent(Stoppable, Protocol):
    def start(self) -> None: ...


class ApplicationInstanceLease(Protocol):
    def close(self) -> None: ...


class ApplicationInstanceGate(Protocol):
    def acquire(self) -> ApplicationInstanceLease | None: ...


class ForegroundWindowMonitor(RuntimeComponent, Protocol):
    pass


class VoiceInputEngine(Protocol):
    """Transport-only Browser Speech engine boundary; callbacks must enter the command queue."""

    def prepare(self, setup_id: VoiceSetupId, language: VoiceLanguage) -> None: ...

    def start_capture(self, capture_id: VoiceCaptureId, language: VoiceLanguage, *, sequence_start: int = 0) -> None: ...

    def stop_capture(self, capture_id: VoiceCaptureId) -> None: ...

    def cancel_capture(self, capture_id: VoiceCaptureId) -> None: ...

    def reset_permission_profile(self) -> None: ...

    def shutdown(self) -> None: ...


class VoiceSetupPresenter(Protocol):
    def show_voice_setup(self) -> None: ...

    def close_voice_setup(self) -> None: ...

    def set_voice_projection(self, projection: VoiceProjection) -> None: ...
