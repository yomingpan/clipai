from __future__ import annotations

from collections.abc import Callable
from typing import cast
import queue

from ClipAI.app.runtime_outputs import ResultOutputRuntimeCommand, ResultOutputRuntimeModule
from ClipAI.app.runtime_provider_configuration import ProviderConfigurationRuntimeModule, ProviderRuntimeCommand
from ClipAI.app.runtime_personal_styles import PersonalStyleRuntimeCommand, PersonalStyleRuntimeModule
from ClipAI.app.runtime_shortcut_guide import ShortcutGuideRuntimeCommand, ShortcutGuideRuntimeModule
from ClipAI.app.runtime_action_feedback import ActionFeedbackRuntimeCommand, ActionFeedbackRuntimeModule
from ClipAI.app.runtime_user_preferences import UserPreferencesRuntimeCommand, UserPreferencesRuntimeModule
from ClipAI.app.runtime_workflows import HeadlessWorkflowFinished, WorkflowInvocationFailed, WorkflowRuntimeCommand, WorkflowRuntimeModule, WorkflowSnapshotReady
from ClipAI.app.runtime_voice_input import VoiceInputRuntimeModule
from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.app.provider_execution import ProviderExecutionModule
from ClipAI.core.commands import ActionFeedbackCompleted, ActivateWorkflow, ArchiveResult, CancelSession, CancelVoiceCapture, ClosePersonalStyles, CloseProviderSettings, CloseSession, CloseShortcutGuide, ControlSurfaceActivated, ControlSurfaceReleased, CopyResult, DisableVoiceInput, EnableVoiceInput, ExportDiagnostics, ExternalForegroundChanged, FollowUp, GuidancePreferencesCompleted, ImportPersonalStyle, InterruptionRequested, InterruptAll, InterruptCurrent, NavigateWorkflowBack, OpenPersonalStyles, OpenProviderSettings, OpenShortcutGuide, OpenVoicePermissionSettings, OpenVoiceSetup, PasteOperationCompleted, PasteResult, PersonalStyleOperationCompleted, RefreshProviderModels, ReloadConfiguration, ResetFirstUseHints, RetryVoiceInputSetup, SelectPersonalStyle, SelectProvider, SelectProviderModel, SelectShortcutGuideItem, SetFirstUseHintsEnabled, SetSpeechSpeed, SetVoiceLanguage, ShortcutAttemptRejected, ShortcutInputEvent, ShortcutKeyStateChanged, ShortcutPressEnded, ShortcutPressInvoked, ShortcutPressStarted, ShutdownApplication, SpeakSelectionOrClipboard, SpeechSpeedPreferencesCompleted, StartAction, StartPopupVoiceCapture, StopVoiceCapture, SubmitActionFeedback, TogglePin, ToggleSpeech, UpdateVoiceDraft, ValidateAndSaveProviderSettings, VoiceCaptureWatchdogExpired, VoiceDisablePreferenceSaved, VoiceDisableShutdownCompleted, VoiceEngineEventReceived, VoiceLanguagePreferenceSaved, VoicePreferenceSaved, VoiceSilenceWatchdogExpired, WorkflowAttentionCompleted
from ClipAI.core.models import ControlSurfaceRef, InterruptionPlan, ShortcutObservationSnapshot
from ClipAI.core.ports import ApplicationView, ForegroundWindowMonitor, OperationTracker, RuntimeComponent, ShortcutInput, ShortcutObservationLease
from ClipAI.services.provider_configuration import ProviderConfigurationResult
from ClipAI.services.shortcut_catalog import ShortcutCatalog
from ClipAI.services.user_control import UserControlCoordinator


_WORKFLOW_COMMANDS = (StartAction, CloseSession, CancelSession, TogglePin, FollowUp, ActivateWorkflow, NavigateWorkflowBack, WorkflowInvocationFailed, HeadlessWorkflowFinished, WorkflowSnapshotReady, WorkflowAttentionCompleted)
_OUTPUT_COMMANDS = (CopyResult, PasteResult, ArchiveResult, ToggleSpeech, SpeakSelectionOrClipboard, ExportDiagnostics)
_PROVIDER_COMMANDS = (SelectProviderModel, SelectProvider, ReloadConfiguration, OpenProviderSettings, CloseProviderSettings, ValidateAndSaveProviderSettings, RefreshProviderModels, ProviderConfigurationResult)
_ACTION_FEEDBACK_COMMANDS = (SubmitActionFeedback, ActionFeedbackCompleted)
_USER_PREFERENCES_COMMANDS = (SetFirstUseHintsEnabled, ResetFirstUseHints, GuidancePreferencesCompleted, SetSpeechSpeed, SpeechSpeedPreferencesCompleted)
_SHORTCUT_GUIDE_COMMANDS = (OpenShortcutGuide, CloseShortcutGuide, SelectShortcutGuideItem)
_PERSONAL_STYLE_COMMANDS = (OpenPersonalStyles, ClosePersonalStyles, ImportPersonalStyle, SelectPersonalStyle, PersonalStyleOperationCompleted)
_SHORTCUT_INPUT_EVENTS = (
    ShortcutKeyStateChanged,
    ShortcutPressStarted,
    ShortcutPressInvoked,
    ShortcutPressEnded,
    ShortcutAttemptRejected,
)
_VOICE_COMMANDS = (OpenVoiceSetup, OpenVoicePermissionSettings, EnableVoiceInput, RetryVoiceInputSetup, DisableVoiceInput, VoiceDisableShutdownCompleted, VoiceDisablePreferenceSaved, VoiceEngineEventReceived, VoicePreferenceSaved, StartPopupVoiceCapture, StopVoiceCapture, CancelVoiceCapture, VoiceCaptureWatchdogExpired, VoiceSilenceWatchdogExpired, SetVoiceLanguage, VoiceLanguagePreferenceSaved, UpdateVoiceDraft)


class AppRuntime:
    """Owns the command queue and desktop runtime lifecycle; modules own command policy."""

    def __init__(
        self,
        *,
        shortcuts: ShortcutCatalog,
        view: ApplicationView,
        supervisor: TaskSupervisor,
        provider_execution: ProviderExecutionModule,
        workflows: WorkflowRuntimeModule,
        result_output: ResultOutputRuntimeModule,
        provider_configuration: ProviderConfigurationRuntimeModule,
        action_feedback: ActionFeedbackRuntimeModule,
        user_preferences: UserPreferencesRuntimeModule,
        hotkey_registrar: Callable[
            [
                dict[str, dict[str, str]],
                Callable[[ShortcutInputEvent], None],
            ],
            ShortcutInput,
        ],
        tray_factory: Callable[[Callable[[], None]], RuntimeComponent] | None = None,
        operation_tracker: OperationTracker | None = None,
        shortcut_guide: ShortcutGuideRuntimeModule | None = None,
        foreground_monitor: ForegroundWindowMonitor | None = None,
        user_control: UserControlCoordinator | None = None,
        voice_input: VoiceInputRuntimeModule | None = None,
        personal_styles: PersonalStyleRuntimeModule | None = None,
    ) -> None:
        self._shortcuts = shortcuts
        self._view = view
        self._supervisor = supervisor
        self._provider_execution = provider_execution
        self._workflow_module = workflows
        self._result_output_module = result_output
        self._provider_configuration_module = provider_configuration
        self._action_feedback_module = action_feedback
        self._user_preferences_module = user_preferences
        self._hotkey_registrar = hotkey_registrar
        self._tray_factory = tray_factory
        self._operation_tracker = operation_tracker
        self._shortcut_guide_module = shortcut_guide
        self._foreground_monitor = foreground_monitor
        self._user_control = user_control or UserControlCoordinator()
        self._voice_input_module = voice_input
        self._personal_styles_module = personal_styles
        self._workflow_module.bind_user_control(self._user_control)
        self._result_output_module.bind_user_control(self._user_control)
        self._provider_configuration_module.bind_user_control(self._user_control)
        self._commands: queue.Queue[object] = queue.Queue()
        self._listener: ShortcutInput | None = None
        self._shortcut_observation: ShortcutObservationLease | None = None
        self._tray: RuntimeComponent | None = None
        self._stopping = False
        self._view.set_command_sink(self.enqueue)

        # Provider configuration compatibility probes remain until that module's
        # tests migrate to constructor-injected presenters.
        self._provider_configuration = provider_configuration.coordinator

    @property
    def _model_selection_presenter(self):
        return self._provider_configuration_module._model_selection_presenter

    @_model_selection_presenter.setter
    def _model_selection_presenter(self, presenter) -> None:
        self._provider_configuration_module._model_selection_presenter = presenter

    @property
    def _provider_selection_presenter(self):
        return self._provider_configuration_module._provider_selection_presenter

    @_provider_selection_presenter.setter
    def _provider_selection_presenter(self, presenter) -> None:
        self._provider_configuration_module._provider_selection_presenter = presenter

    def enqueue(self, command: object) -> None:
        if not self._stopping:
            self._commands.put(command)

    def start(self) -> None:
        if self._foreground_monitor is not None:
            self._foreground_monitor.start()
        self._listener = self._hotkey_registrar(
            self._shortcuts.hotkey_map(),
            self.enqueue,
        )
        if self._tray_factory is not None:
            self._tray = self._tray_factory(lambda: self.enqueue(ShutdownApplication()))
            self._tray.start()

    def run_forever(self) -> None:
        self.start()
        try:
            self._view.run(self.drain_commands)
        finally:
            self.stop()

    def drain_commands(self) -> None:
        while True:
            try:
                command = self._commands.get_nowait()
            except queue.Empty:
                return
            self._route(command)

    def stop(self) -> None:
        if self._stopping:
            return
        self._stopping = True
        if self._foreground_monitor is not None:
            self._foreground_monitor.stop()
        self._workflow_module.stop()
        if self._voice_input_module is not None:
            self._voice_input_module.stop()
        self._result_output_module.stop()
        self._close_shortcut_observation()
        if self._listener is not None:
            self._listener.stop()
        self._listener = None
        if self._tray is not None:
            self._tray.stop()
        self._tray = None
        self._provider_execution.shutdown()
        self._supervisor.shutdown()
        if self._operation_tracker is not None:
            self._operation_tracker.stop()
        self._view.stop()

    def show_last_error(self) -> None:
        self._workflow_module.show_last_error()

    def _route(self, command: object) -> None:
        if isinstance(command, InterruptionRequested):
            self._route(InterruptCurrent() if command.scope == "current" else InterruptAll())
        elif isinstance(command, _SHORTCUT_INPUT_EVENTS):
            if isinstance(command, (ShortcutPressStarted, ShortcutPressInvoked, ShortcutPressEnded)) and self._shortcuts.is_push_to_talk(command.shortcut_id):
                if self._voice_input_module is not None and isinstance(command, ShortcutPressStarted):
                    self._voice_input_module.handle_shortcut_started(command)
                elif self._voice_input_module is not None and isinstance(command, ShortcutPressEnded):
                    self._voice_input_module.handle_shortcut_ended(command)
                return
            if self._shortcut_guide_module is not None and self._shortcut_guide_module.consume(command):
                return
            if isinstance(command, ShortcutPressInvoked):
                resolved = self._workflow_module.resolve_shortcut(command)
                if resolved is not None:
                    self._route(resolved)
            elif isinstance(command, ShortcutAttemptRejected):
                self._workflow_module.reject_shortcut_attempt()
        elif isinstance(command, ExternalForegroundChanged):
            self._result_output_module.observe_paste_target(command.target)
        elif isinstance(command, ShutdownApplication):
            self.stop()
        elif isinstance(command, ControlSurfaceActivated):
            self._user_control.focus(command.surface)
        elif isinstance(command, ControlSurfaceReleased):
            self._user_control.release(command.surface)
        elif isinstance(command, InterruptCurrent):
            if (
                self._user_control.focused_surface is None
                and self._workflow_module.has_pending_shortcut_sequence()
            ):
                self._workflow_module.cancel_shortcut_sequence()
                return
            self._execute_interruption(self._user_control.interrupt_current())
        elif isinstance(command, InterruptAll):
            self._execute_interruption(self._user_control.interrupt_all())
            task_ids = (
                *self._workflow_module.cancel_all_content_operations(),
                *self._result_output_module.cancel_all_content_operations(),
            )
            self._supervisor.cancel_many(task_ids, lambda: None)
        elif isinstance(command, CloseSession):
            self._user_control.release(ControlSurfaceRef(command.session_id, "workflow"))
            if self._voice_input_module is not None:
                self._voice_input_module.close_workflow(command.session_id)
            self._result_output_module.close_workflow(command.session_id)
            self._workflow_module.handle(command)
        elif isinstance(command, ActivateWorkflow):
            self._user_control.focus(ControlSurfaceRef(command.workflow_id, "workflow"))
            self._workflow_module.handle(command)
        elif isinstance(command, OpenShortcutGuide):
            self._user_control.focus(ControlSurfaceRef(command.guide_id, "shortcut_guide"))
            if self._shortcut_guide_module is not None:
                self._workflow_module.cancel_shortcut_sequence()
                observation = ShortcutObservationSnapshot()
                if not self._shortcut_guide_module.is_open and self._listener is not None:
                    self._shortcut_observation = self._listener.observe()
                    observation = self._shortcut_observation.snapshot
                self._shortcut_guide_module.handle(command, observation)
        elif isinstance(command, CloseShortcutGuide):
            self._user_control.release(ControlSurfaceRef(command.guide_id, "shortcut_guide"))
            if self._shortcut_guide_module is not None:
                self._shortcut_guide_module.handle(command)
                if not self._shortcut_guide_module.is_open:
                    self._close_shortcut_observation()
            else:
                self._close_shortcut_observation()
        elif isinstance(command, _SHORTCUT_GUIDE_COMMANDS):
            if self._shortcut_guide_module is not None:
                self._shortcut_guide_module.handle(cast(ShortcutGuideRuntimeCommand, command))
        elif isinstance(command, OpenProviderSettings):
            self._user_control.focus(ControlSurfaceRef("provider-settings", "provider_settings"))
            self._provider_configuration_module.handle(command)
        elif isinstance(command, CloseProviderSettings):
            self._user_control.release(ControlSurfaceRef("provider-settings", "provider_settings"))
            self._provider_configuration_module.handle(command)
        elif isinstance(command, OpenPersonalStyles):
            self._user_control.focus(ControlSurfaceRef("personal-styles", "personal_styles"))
            if self._personal_styles_module is not None:
                self._personal_styles_module.handle(command)
        elif isinstance(command, ClosePersonalStyles):
            self._user_control.release(ControlSurfaceRef("personal-styles", "personal_styles"))
            if self._personal_styles_module is not None:
                self._personal_styles_module.handle(command)
        elif isinstance(command, _PERSONAL_STYLE_COMMANDS):
            if self._personal_styles_module is not None:
                self._personal_styles_module.handle(cast(PersonalStyleRuntimeCommand, command))
        elif isinstance(command, PasteOperationCompleted):
            self._result_output_module.handle(command)
            if self._workflow_module.observe_paste_completion(command):
                self._user_control.release(ControlSurfaceRef(command.workflow_id, "workflow"))
        elif isinstance(command, _WORKFLOW_COMMANDS):
            self._workflow_module.handle(cast(WorkflowRuntimeCommand, command))
        elif isinstance(command, _OUTPUT_COMMANDS):
            self._result_output_module.handle(cast(ResultOutputRuntimeCommand, command))
        elif isinstance(command, _PROVIDER_COMMANDS):
            self._provider_configuration_module.handle(cast(ProviderRuntimeCommand, command))
        elif isinstance(command, _ACTION_FEEDBACK_COMMANDS):
            self._action_feedback_module.handle(cast(ActionFeedbackRuntimeCommand, command))
        elif isinstance(command, _USER_PREFERENCES_COMMANDS):
            self._user_preferences_module.handle(cast(UserPreferencesRuntimeCommand, command))
        elif self._voice_input_module is not None and isinstance(command, _VOICE_COMMANDS):
            self._voice_input_module.handle(command)

    def _execute_interruption(self, plan: InterruptionPlan) -> None:
        surface = plan.surface
        if surface is not None:
            if surface.kind == "workflow":
                self._route(CloseSession(surface.surface_id))
            elif surface.kind == "provider_settings":
                self._route(CloseProviderSettings())
            elif surface.kind == "shortcut_guide":
                self._route(CloseShortcutGuide(surface.surface_id))
            elif surface.kind == "personal_styles":
                self._route(ClosePersonalStyles())
        for operation in plan.operations:
            if operation.kind == "workflow":
                self._workflow_module.cancel_operation(operation.operation_id)
            elif operation.kind == "provider_configuration":
                self._provider_configuration_module.handle(CloseProviderSettings())
            elif operation.kind == "shortcut_sequence":
                self._workflow_module.cancel_shortcut_sequence()
            else:
                self._result_output_module.cancel_operation(operation.operation_id)

    def _close_shortcut_observation(self) -> None:
        lease, self._shortcut_observation = self._shortcut_observation, None
        if lease is not None:
            lease.close()
