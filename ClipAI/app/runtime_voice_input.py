from __future__ import annotations

import uuid
import threading
from collections.abc import Callable

from ClipAI.app.runtime_workflows import WorkflowRuntimeModule
from ClipAI.core.commands import CancelVoiceCapture, DisableVoiceInput, EnableVoiceInput, OpenVoicePermissionSettings, OpenVoiceSetup, RetryVoiceInputSetup, SetVoiceLanguage, ShortcutPressEnded, ShortcutPressStarted, StopVoiceCapture, UpdateVoiceDraft, VoiceCaptureWatchdogExpired, VoiceDisableShutdownCompleted, VoiceDisablePreferenceSaved, VoiceEngineEventReceived, VoiceLanguagePreferenceSaved, VoicePreferenceSaved
from ClipAI.core.models import ControlSurfaceRef, PasteTarget, ShortcutPressId
from ClipAI.core.ports import UserNotifier, VoiceInputEngine, VoiceSetupPresenter
from ClipAI.core.voice import VoiceCapabilityPhase, VoiceDraftTarget, VoiceEngineSetupFailed, VoiceLanguageChangeId, VoiceProjection, VoiceTransportFailure
from ClipAI.services.voice_input import CancelVoiceCapture as CancelVoiceCaptureEffect
from ClipAI.services.voice_input import FinalizeVoiceDraft, PersistVoiceDisabled, PersistVoiceEnabled, PersistVoiceLanguage, PrepareVoiceSetup, RestoreVoiceReview, ShutdownVoiceEngine, StartVoiceCapture, StopVoiceCapture as StopVoiceCaptureEffect, VoiceEffect, VoiceInputController, VoiceTransition


VOICE_CAPTURE_WATCHDOG_SECONDS = 120.0


def _schedule_watchdog(delay_seconds: float, callback: Callable[[], None]) -> threading.Timer:
    timer = threading.Timer(delay_seconds, callback)
    timer.daemon = True
    timer.start()
    return timer


class VoiceInputRuntimeModule:
    """Routes typed Voice effects without retaining Voice domain state."""

    def __init__(
        self,
        *,
        controller: VoiceInputController,
        engine: VoiceInputEngine,
        workflows: WorkflowRuntimeModule,
        paste_target_reader: Callable[[], PasteTarget | None],
        capture_external_target: Callable[[], PasteTarget | None] = lambda: None,
        persist_enabled: Callable[[str], None] = lambda _setup_id: None,
        persist_disabled: Callable[[str], None] = lambda _disable_id: None,
        persist_language: Callable[[str, str], None] = lambda _operation_id, _language: None,
        complete_voice_preference: Callable[[str, str], None] = lambda _operation_id, _error: None,
        dispatch: Callable[[object], None] = lambda _command: None,
        projection_sink: Callable[[VoiceProjection], None] = lambda _projection: None,
        setup_presenter: VoiceSetupPresenter | None = None,
        focused_surface_reader: Callable[[], ControlSurfaceRef | None] = lambda: None,
        open_permission_settings: Callable[[], None] = lambda: None,
        watchdog_schedule: Callable[[float, Callable[[], None]], object] = _schedule_watchdog,
        notifier: UserNotifier | None = None,
    ) -> None:
        self._controller = controller
        self._engine = engine
        self._workflows = workflows
        self._paste_target_reader = paste_target_reader
        self._capture_external_target = capture_external_target
        self._persist_enabled = persist_enabled
        self._persist_disabled = persist_disabled
        self._persist_language = persist_language
        self._complete_voice_preference = complete_voice_preference
        self._dispatch = dispatch
        self._projection_sink = projection_sink
        self._setup_presenter = setup_presenter
        self._focused_surface_reader = focused_surface_reader
        self._open_permission_settings = open_permission_settings
        self._watchdog_schedule = watchdog_schedule
        self._notifier = notifier
        self._watchdogs: dict[ShortcutPressId, object] = {}

    def handle_shortcut_started(self, command: ShortcutPressStarted) -> bool:
        focused_surface = self._focused_surface_reader()
        admission = self._workflows.admit_voice_shortcut(
            focused_surface,
            self._controller.projection.workflow_id,
        )
        if admission.kind == "rejected":
            self._notify_shortcut_rejected(admission.message)
            return False
        if admission.kind == "continue":
            return True
        if self._controller.projection.capability is VoiceCapabilityPhase.SETUP_REQUIRED:
            if self._setup_presenter is not None:
                self._setup_presenter.show_voice_setup()
            return True
        if admission.kind == "voice_review":
            assert admission.target is not None
            frozen = admission.target
        else:
            target = self._capture_external_target() or self._paste_target_reader()
            if target is None:
                self._notify_shortcut_rejected("Focus the app where you want to dictate, then try again.")
                return False
            workflow_id = uuid.uuid4().hex
            frozen = VoiceDraftTarget(workflow_id, 0, target, 0, 0)
        transition = self._controller.request_capture_for_press(command.press_id, frozen)
        if transition.ignored:
            self._notify_shortcut_rejected("Voice Input is already active.")
            return False
        if admission.kind == "create":
            self._workflows.create_voice_workflow(frozen.workflow_id, frozen.paste_target)
        self._start_watchdog(command.press_id)
        self._execute(transition)
        return True

    def _notify_shortcut_rejected(self, message: str) -> None:
        if self._notifier is not None:
            self._notifier.notify("Voice Input", message)

    def handle_shortcut_ended(self, command: ShortcutPressEnded) -> bool:
        transition = (
            self._controller.abandon_press(command.press_id)
            if command.outcome == "cancelled"
            else self._controller.request_release_for_press(command.press_id)
        )
        if transition.ignored:
            return False
        self._cancel_watchdog(command.press_id)
        self._execute(transition)
        return True

    def close_workflow(self, workflow_id: str) -> bool:
        transition = self._controller.cancel_capture_for_workflow(workflow_id)
        if transition.ignored:
            return False
        self._cancel_all_watchdogs()
        self._execute(transition)
        return True

    def handle(self, command: OpenVoiceSetup | OpenVoicePermissionSettings | EnableVoiceInput | RetryVoiceInputSetup | DisableVoiceInput | VoiceDisableShutdownCompleted | VoiceDisablePreferenceSaved | VoiceEngineEventReceived | VoicePreferenceSaved | StopVoiceCapture | CancelVoiceCapture | VoiceCaptureWatchdogExpired | SetVoiceLanguage | VoiceLanguagePreferenceSaved | UpdateVoiceDraft) -> bool:
        if isinstance(command, OpenVoiceSetup):
            if self._setup_presenter is not None:
                self._setup_presenter.show_voice_setup()
            return True
        if isinstance(command, OpenVoicePermissionSettings):
            self._open_permission_settings()
            return True
        if isinstance(command, RetryVoiceInputSetup):
            transition = self._controller.request_setup(command.setup_id)
            if transition.ignored:
                return False
            try:
                self._engine.reset_permission_profile()
            except OSError:
                transition = self._controller.complete_setup(VoiceEngineSetupFailed(
                    command.setup_id,
                    VoiceTransportFailure.INITIALIZATION_FAILED,
                    "ClipAI could not reset its microphone permission. Close any ClipAI helper windows and try again.",
                ))
            self._execute(transition)
            return True
        if isinstance(command, VoiceCaptureWatchdogExpired):
            self._cancel_watchdog(command.press_id)
            transition = self._controller.expire_capture_watchdog(command.press_id)
        elif isinstance(command, EnableVoiceInput):
            transition = self._controller.request_setup(command.setup_id)
        elif isinstance(command, DisableVoiceInput):
            transition = self._controller.request_disable(command.disable_id)
        elif isinstance(command, VoiceDisableShutdownCompleted):
            transition = self._controller.complete_disable_shutdown(command.disable_id, command.error)
        elif isinstance(command, VoiceDisablePreferenceSaved):
            self._complete_voice_preference(command.disable_id, command.error)
            transition = self._controller.complete_disable_preference(command.disable_id, command.error)
        elif isinstance(command, VoiceEngineEventReceived):
            transition = self._controller.observe_engine(command.event)
        elif isinstance(command, VoicePreferenceSaved):
            self._complete_voice_preference(command.setup_id, command.error)
            transition = self._controller.complete_enable_save(command.setup_id, command.error)
        elif isinstance(command, StopVoiceCapture):
            transition = self._controller.request_stop(command.capture_id)
        elif isinstance(command, SetVoiceLanguage):
            operation_id = command.operation_id or VoiceLanguageChangeId(uuid.uuid4().hex)
            transition = self._controller.set_language(command.language, operation_id)
        elif isinstance(command, VoiceLanguagePreferenceSaved):
            self._complete_voice_preference(command.operation_id, command.error)
            transition = self._controller.complete_language_save(command.operation_id, command.error)
        elif isinstance(command, UpdateVoiceDraft):
            controller = self._workflows.controller_for(command.workflow_id)
            return controller is not None and controller.edit_voice_draft(command.expected_revision, command.text) is not None
        else:
            transition = self._controller.request_cancel(command.capture_id)
        if transition.ignored:
            return False
        if isinstance(command, (DisableVoiceInput, StopVoiceCapture, CancelVoiceCapture)):
            self._cancel_all_watchdogs()
        self._execute(transition)
        return True

    def stop(self) -> None:
        self._cancel_all_watchdogs()
        self._engine.shutdown()

    def _execute(self, transition: VoiceTransition) -> None:
        if transition.projection.capture_id is None:
            self._cancel_all_watchdogs()
        self._projection_sink(transition.projection)
        if self._setup_presenter is not None:
            self._setup_presenter.set_voice_projection(transition.projection)
        if transition.projection.capability is VoiceCapabilityPhase.READY and self._setup_presenter is not None:
            self._setup_presenter.close_voice_setup()
        elif (
            transition.projection.capability is VoiceCapabilityPhase.PERMISSION_BLOCKED
            and transition.projection.capture_id is None
            and self._setup_presenter is not None
        ):
            self._setup_presenter.show_voice_setup()
        if transition.projection.workflow_id is not None:
            controller = self._workflows.controller_for(transition.projection.workflow_id)
            if controller is not None:
                controller.project_voice_capture(transition.projection)
        for effect in transition.effects:
            self._execute_effect(effect)

    def _execute_effect(self, effect: VoiceEffect) -> None:
        if isinstance(effect, PrepareVoiceSetup):
            self._engine.prepare(effect.setup_id, effect.language)
        elif isinstance(effect, PersistVoiceEnabled):
            self._persist_enabled(effect.setup_id)
        elif isinstance(effect, PersistVoiceDisabled):
            self._persist_disabled(effect.disable_id)
        elif isinstance(effect, PersistVoiceLanguage):
            self._persist_language(effect.operation_id, effect.language)
        elif isinstance(effect, ShutdownVoiceEngine):
            try:
                self._engine.shutdown()
            except Exception as exc:
                self._dispatch(VoiceDisableShutdownCompleted(effect.disable_id, str(exc)))
            else:
                self._dispatch(VoiceDisableShutdownCompleted(effect.disable_id))
        elif isinstance(effect, StartVoiceCapture):
            self._engine.start_capture(effect.capture_id, effect.language, sequence_start=effect.sequence_start)
        elif isinstance(effect, StopVoiceCaptureEffect):
            self._engine.stop_capture(effect.capture_id)
        elif isinstance(effect, CancelVoiceCaptureEffect):
            self._engine.cancel_capture(effect.capture_id)
        elif isinstance(effect, RestoreVoiceReview):
            controller = self._workflows.controller_for(effect.target.workflow_id)
            if controller is not None:
                controller.restore_voice_review(effect.target, effect.message)
        else:
            controller = self._workflows.controller_for(effect.target.workflow_id)
            if controller is not None:
                controller.apply_voice_finalization(effect.target, effect.text)

    def _start_watchdog(self, press_id: ShortcutPressId) -> None:
        self._cancel_watchdog(press_id)
        self._watchdogs[press_id] = self._watchdog_schedule(
            VOICE_CAPTURE_WATCHDOG_SECONDS,
            lambda: self._dispatch(VoiceCaptureWatchdogExpired(press_id)),
        )

    def _cancel_watchdog(self, press_id: ShortcutPressId) -> None:
        watchdog = self._watchdogs.pop(press_id, None)
        if watchdog is not None and hasattr(watchdog, "cancel"):
            watchdog.cancel()

    def _cancel_all_watchdogs(self) -> None:
        for press_id in tuple(self._watchdogs):
            self._cancel_watchdog(press_id)
