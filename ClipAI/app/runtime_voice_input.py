from __future__ import annotations

import uuid
import threading
import time
from collections.abc import Callable
from typing import Protocol

from ClipAI.app.voice_capture_timing import VoiceCaptureTiming
from ClipAI.app.runtime_workflows import VoiceCaptureIntent, WorkflowRuntimeModule
from ClipAI.core.commands import ToggleInlineDictation, ConfirmInlineDictation, InlineDictationRefineSettled, VoiceFinalizeWatchdogExpired
from ClipAI.core.commands import CancelVoiceCapture, DisableVoiceInput, EnableVoiceInput, OpenVoicePermissionSettings, OpenVoiceSetup, RetryVoiceInputSetup, SetVoiceLanguage, ShortcutPressEnded, ShortcutPressInvoked, ShortcutPressStarted, StartPopupVoiceCapture, StopVoiceCapture, UpdateVoiceDraft, VoiceCaptureCountdownTick, VoiceCaptureCountdownTickForCapture, VoiceCaptureHoldElapsed, VoiceCaptureTimeout, VoiceCaptureWatchdogExpired, VoiceDisableShutdownCompleted, VoiceDisablePreferenceSaved, VoiceEngineEventReceived, VoiceLanguagePreferenceSaved, VoicePreferenceSaved, VoiceSilenceWatchdogExpired
from ClipAI.core.models import ControlSurfaceRef, PasteTarget, ShortcutPressId
from ClipAI.core.ports import InlineDictationPresenter, UserNotifier, VoiceInputEngine, VoiceSetupPresenter
from ClipAI.core.voice import VoiceCapabilityPhase, VoiceCaptureId, VoiceCapturePhase, VoiceCaptureTarget, VoiceDraftTarget, VoiceInlineTarget, VoiceEngineSetupFailed, VoiceLanguageChangeId, VoiceProjection, VoiceTransportFailure
from ClipAI.services.voice_input import CancelVoiceCapture as CancelVoiceCaptureEffect
from ClipAI.services.voice_input import FinalizeVoiceDraft, FinalizeVoiceFollowUp, PersistVoiceDisabled, PersistVoiceEnabled, PersistVoiceLanguage, PrepareVoiceSetup, RestoreVoiceFollowUp, RestoreVoiceReview, ShutdownVoiceEngine, StartVoiceCapture, StopVoiceCapture as StopVoiceCaptureEffect, VoiceEffect, VoiceInputController, VoiceTransition
from ClipAI.services.voice_input import PresentInlineChoice, PasteInlineDictation, DiscardInlineDictation


VOICE_MIC_HOLD_SECONDS = 0.18


def _schedule_watchdog(delay_seconds: float, callback: Callable[[], None]) -> threading.Timer:
    timer = threading.Timer(delay_seconds, callback)
    timer.daemon = True
    timer.start()
    return timer


class _CancellableTimer(Protocol):
    def cancel(self) -> None: ...


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
        hold_schedule: Callable[[float, Callable[[], None]], _CancellableTimer] = _schedule_watchdog,
        monotonic_clock: Callable[[], float] = time.monotonic,
        notifier: UserNotifier | None = None,
        inline_presenter: InlineDictationPresenter | None = None,
        paste_inline: Callable[[str, PasteTarget, bool, str], None] = lambda _text, _target, _refine, _workflow_id: None,
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
        self._hold_schedule = hold_schedule
        self._notifier = notifier
        self._inline_presenter = inline_presenter
        self._paste_inline = paste_inline
        self._timing = VoiceCaptureTiming(watchdog_schedule, monotonic_clock, dispatch, controller.press_id_for_capture)
        self._pending_presses: dict[ShortcutPressId, VoiceCaptureTarget] = {}
        self._hold_timers: dict[ShortcutPressId, _CancellableTimer] = {}
        self._capturing_presses: set[ShortcutPressId] = set()

    def admit_entry_panel_open(self) -> bool:
        if not self._pending_presses and self._controller.projection.capture_phase not in {
            VoiceCapturePhase.STARTING,
            VoiceCapturePhase.LISTENING,
            VoiceCapturePhase.STOP_REQUESTED,
            VoiceCapturePhase.FINALIZING,
            VoiceCapturePhase.CANCEL_REQUESTED,
        }:
            return True
        self._notify_shortcut_rejected(
            "Voice Input is active. Finish or cancel it before opening the Action panel."
        )
        return False

    def handle_shortcut_started(self, command: ShortcutPressStarted) -> bool:
        if self._controller.has_pending_inline_choice():
            self._notify_shortcut_rejected("Finish or cancel the pending dictation first.")
            return False
        focused_surface = self._focused_surface_reader()
        admission = self._workflows.admit_voice_capture(VoiceCaptureIntent(
            "shortcut",
            focused_surface=focused_surface,
            active_voice_workflow_id=self._controller.projection.workflow_id,
        ))
        if admission.kind == "rejected":
            self._notify_shortcut_rejected(admission.message)
            return False
        if admission.kind == "continue":
            return True
        if self._controller.projection.capability is VoiceCapabilityPhase.SETUP_REQUIRED:
            if self._setup_presenter is not None:
                self._setup_presenter.show_voice_setup()
            return True
        if admission.kind in {"voice_review", "follow_up"}:
            assert admission.target is not None
            frozen = admission.target
        else:
            target = self._capture_external_target() or self._paste_target_reader()
            workflow_id = admission.workflow_id or uuid.uuid4().hex
            frozen = VoiceDraftTarget(workflow_id, 0, target, 0, 0)
        if admission.kind == "create":
            assert isinstance(frozen, VoiceDraftTarget)
            self._workflows.create_voice_workflow(frozen.workflow_id, frozen.paste_target)
        self._pending_presses[command.press_id] = frozen
        self._arm_mic_hold(command.press_id)
        return True

    def _notify_shortcut_rejected(self, message: str) -> None:
        if self._notifier is not None:
            self._notifier.notify("Voice Input", message)

    def handle_shortcut_invoked(self, command: ShortcutPressInvoked) -> bool:
        return True

    def handle_shortcut_ended(self, command: ShortcutPressEnded) -> bool:
        self._cancel_mic_hold(command.press_id)
        armed = self._pending_presses.pop(command.press_id, None) is not None
        capturing = command.press_id in self._capturing_presses
        self._capturing_presses.discard(command.press_id)
        if not capturing:
            return armed
        if command.outcome == "cancelled":
            transition = self._controller.abandon_press(command.press_id)
        else:
            transition = self._controller.request_release_for_press(command.press_id)
        if transition.ignored:
            return False
        self._execute(transition)
        return True

    def close_workflow(self, workflow_id: str) -> bool:
        self._cancel_all_mic_holds()
        transition = self._controller.cancel_capture_for_workflow(workflow_id)
        if transition.ignored:
            return False
        self._execute(transition)
        return True

    def _start_popup_capture(self, command: StartPopupVoiceCapture) -> VoiceTransition:
        admission = self._workflows.admit_voice_capture(
            VoiceCaptureIntent("popup", workflow_id=command.workflow_id)
        )
        if admission.kind not in {"voice_review", "follow_up"} or admission.target is None:
            return VoiceTransition(self._controller.projection, ignored=True)
        return self._controller.request_capture(command.capture_id, admission.target)

    def toggle_inline_dictation(self) -> bool:
        active = self._controller.active_inline_capture_id()
        if active is not None:
            transition = self._controller.request_stop(active)
        else:
            if self._controller.has_pending_inline_choice():
                self._notify_shortcut_rejected("Finish or cancel the pending dictation first.")
                return False
            if self._controller.projection.capability is VoiceCapabilityPhase.SETUP_REQUIRED:
                if self._setup_presenter is not None:
                    self._setup_presenter.show_voice_setup()
                return True
            target = self._capture_external_target() or self._paste_target_reader()
            capture_id = VoiceCaptureId(f"inline-{uuid.uuid4().hex}")
            transition = self._controller.request_capture(
                capture_id, VoiceInlineTarget(str(capture_id), target)
            )
            if not transition.ignored and self._inline_presenter is not None:
                self._inline_presenter.open_inline_dictation()
        if transition.ignored:
            self._notify_shortcut_rejected("Voice Input is busy. Finish or cancel the current dictation.")
            return False
        self._execute(transition)
        return True

    def cancel_inline_dictation(self) -> bool:
        transition = self._controller.cancel_inline()
        if transition.ignored:
            return False
        self._execute(transition)
        if self._inline_presenter is not None:
            self._inline_presenter.close_inline_dictation()
        return True

    def handle(self, command: OpenVoiceSetup | OpenVoicePermissionSettings | EnableVoiceInput | RetryVoiceInputSetup | DisableVoiceInput | VoiceDisableShutdownCompleted | VoiceDisablePreferenceSaved | VoiceEngineEventReceived | VoicePreferenceSaved | StartPopupVoiceCapture | StopVoiceCapture | CancelVoiceCapture | VoiceCaptureHoldElapsed | VoiceCaptureCountdownTick | VoiceCaptureCountdownTickForCapture | VoiceCaptureTimeout | VoiceCaptureWatchdogExpired | VoiceFinalizeWatchdogExpired | VoiceSilenceWatchdogExpired | ToggleInlineDictation | ConfirmInlineDictation | InlineDictationRefineSettled | SetVoiceLanguage | VoiceLanguagePreferenceSaved | UpdateVoiceDraft) -> bool:
        if isinstance(command, ToggleInlineDictation):
            return self.toggle_inline_dictation()
        if isinstance(command, ConfirmInlineDictation):
            transition = self._controller.confirm_inline_settlement(command.refine)
            if transition.ignored:
                return False
            self._execute(transition)
            return True
        if isinstance(command, InlineDictationRefineSettled):
            if self._inline_presenter is not None:
                self._inline_presenter.close_inline_dictation(workflow_id=command.workflow_id)
            return True
        if isinstance(command, VoiceCaptureHoldElapsed):
            return self._open_mic_for_press(command.press_id)
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
            transition = self._controller.expire_capture_watchdog(command.press_id)
        elif isinstance(command, VoiceCaptureCountdownTick):
            transition = self._controller.note_capture_countdown(
                command.press_id,
                command.remaining_seconds,
            )
        elif isinstance(command, VoiceCaptureCountdownTickForCapture):
            transition = self._controller.note_capture_countdown_for_capture(
                command.capture_id,
                command.remaining_seconds,
            )
        elif isinstance(command, VoiceCaptureTimeout):
            transition = self._controller.request_stop(command.capture_id)
        elif isinstance(command, VoiceFinalizeWatchdogExpired):
            transition = self._controller.force_settle_pending_stop(command.capture_id)
        elif isinstance(command, VoiceSilenceWatchdogExpired):
            transition = self._controller.note_silence_timeout(command.capture_id)
        elif isinstance(command, StartPopupVoiceCapture):
            transition = self._start_popup_capture(command)
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
        self._execute(transition)
        return True

    def stop(self) -> None:
        self._cancel_all_mic_holds()
        self._timing.cancel_all()
        if self._inline_presenter is not None:
            self._inline_presenter.close_inline_dictation()
        self._engine.shutdown()

    def _open_mic_for_press(self, press_id: ShortcutPressId) -> bool:
        self._cancel_mic_hold(press_id)
        target = self._pending_presses.pop(press_id, None)
        if target is None:
            return False
        transition = self._controller.request_capture_for_press(press_id, target)
        if transition.ignored:
            return False
        self._capturing_presses.add(press_id)
        self._execute(transition)
        return True

    def _arm_mic_hold(self, press_id: ShortcutPressId) -> None:
        self._cancel_mic_hold(press_id)
        self._hold_timers[press_id] = self._hold_schedule(
            VOICE_MIC_HOLD_SECONDS,
            lambda: self._hold_timer_elapsed(press_id),
        )

    def _hold_timer_elapsed(self, press_id: ShortcutPressId) -> None:
        if press_id in self._hold_timers:
            self._dispatch(VoiceCaptureHoldElapsed(press_id))

    def _cancel_mic_hold(self, press_id: ShortcutPressId) -> None:
        timer = self._hold_timers.pop(press_id, None)
        if timer is not None:
            timer.cancel()

    def _cancel_all_mic_holds(self) -> None:
        for press_id in tuple(self._hold_timers):
            self._cancel_mic_hold(press_id)
        self._pending_presses.clear()

    def _execute(self, transition: VoiceTransition) -> None:
        self._timing.observe(transition.projection)
        if (
            transition.projection.capture_phase is VoiceCapturePhase.LISTENING
            and transition.projection.remaining_seconds is None
            and transition.projection.capture_id is not None
        ):
            capture_id = transition.projection.capture_id
            press_id = self._controller.press_id_for_capture(capture_id)
            countdown = (
                self._controller.note_capture_countdown(press_id, 120)
                if press_id is not None
                else self._controller.note_capture_countdown_for_capture(capture_id, 120)
            )
            if not countdown.ignored:
                transition = countdown
        self._projection_sink(transition.projection)
        if self._controller.active_inline_capture_id() is not None and self._inline_presenter is not None:
            self._inline_presenter.update_inline_dictation(transition.projection)
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
        elif isinstance(effect, PresentInlineChoice):
            if self._inline_presenter is not None:
                self._inline_presenter.present_inline_choice(effect.text)
        elif isinstance(effect, PasteInlineDictation):
            self._paste_inline(effect.text, effect.target, effect.refine, effect.workflow_id)
            if not effect.refine and self._inline_presenter is not None:
                self._inline_presenter.close_inline_dictation()
        elif isinstance(effect, DiscardInlineDictation):
            if self._inline_presenter is not None:
                self._inline_presenter.close_inline_dictation(flash_failure=bool(effect.message), message=effect.message)
        elif isinstance(effect, FinalizeVoiceDraft):
            controller = self._workflows.controller_for(effect.target.workflow_id)
            if controller is not None:
                controller.apply_voice_finalization(effect.target, effect.text, effect.warning)
        elif isinstance(effect, RestoreVoiceFollowUp):
            controller = self._workflows.controller_for(effect.target.workflow_id)
            if controller is not None:
                controller.restore_voice_follow_up(effect.capture_id, effect.target, effect.message)
        else:
            assert isinstance(effect, FinalizeVoiceFollowUp)
            controller = self._workflows.controller_for(effect.target.workflow_id)
            if controller is not None:
                controller.apply_voice_follow_up_finalization(
                    effect.capture_id,
                    effect.target,
                    effect.text,
                    effect.warning,
                )
