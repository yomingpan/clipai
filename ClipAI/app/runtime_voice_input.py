from __future__ import annotations

import uuid
import threading
import math
import time
from collections.abc import Callable

from ClipAI.app.runtime_workflows import VoiceCaptureIntent, WorkflowRuntimeModule
from ClipAI.core.commands import CancelVoiceCapture, DisableVoiceInput, EnableVoiceInput, OpenVoicePermissionSettings, OpenVoiceSetup, RetryVoiceInputSetup, SetVoiceLanguage, ShortcutPressEnded, ShortcutPressStarted, StartPopupVoiceCapture, StopVoiceCapture, UpdateVoiceDraft, VoiceCaptureCountdownTick, VoiceCaptureCountdownTickForCapture, VoiceCaptureTimeout, VoiceCaptureWatchdogExpired, VoiceDisableShutdownCompleted, VoiceDisablePreferenceSaved, VoiceEngineEventReceived, VoiceLanguagePreferenceSaved, VoicePreferenceSaved, VoiceSilenceWatchdogExpired
from ClipAI.core.models import ControlSurfaceRef, PasteTarget, ShortcutPressId
from ClipAI.core.ports import UserNotifier, VoiceInputEngine, VoiceSetupPresenter
from ClipAI.core.voice import VoiceCapabilityPhase, VoiceCaptureId, VoiceCapturePhase, VoiceDraftTarget, VoiceEngineListening, VoiceEngineSetupFailed, VoiceLanguageChangeId, VoiceProjection, VoiceTransportFailure
from ClipAI.services.voice_input import CancelVoiceCapture as CancelVoiceCaptureEffect
from ClipAI.services.voice_input import FinalizeVoiceDraft, FinalizeVoiceFollowUp, PersistVoiceDisabled, PersistVoiceEnabled, PersistVoiceLanguage, PrepareVoiceSetup, RestoreVoiceFollowUp, RestoreVoiceReview, ShutdownVoiceEngine, StartVoiceCapture, StopVoiceCapture as StopVoiceCaptureEffect, VoiceEffect, VoiceInputController, VoiceTransition


VOICE_CAPTURE_WATCHDOG_SECONDS = 120.0
VOICE_SILENCE_HINT_SECONDS = 2.0


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
        monotonic_clock: Callable[[], float] = time.monotonic,
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
        self._monotonic_clock = monotonic_clock
        self._notifier = notifier
        self._watchdogs: dict[ShortcutPressId, object] = {}
        self._countdown_watchdogs: dict[ShortcutPressId, object] = {}
        self._capture_countdown_watchdogs: dict[VoiceCaptureId, object] = {}
        self._capture_deadlines: dict[ShortcutPressId, float] = {}
        self._capture_deadlines_by_id: dict[VoiceCaptureId, float] = {}
        self._silence_watchdogs: dict[VoiceCaptureId, object] = {}

    def admit_entry_panel_open(self) -> bool:
        if self._controller.projection.capture_phase not in {
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
        transition = self._controller.request_capture_for_press(command.press_id, frozen)
        if transition.ignored:
            self._notify_shortcut_rejected("Voice Input is already active.")
            return False
        if admission.kind == "create":
            assert isinstance(frozen, VoiceDraftTarget)
            self._workflows.create_voice_workflow(frozen.workflow_id, frozen.paste_target)
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
        self._cancel_all_silence_watchdogs()
        self._execute(transition)
        return True

    def _start_popup_capture(self, command: StartPopupVoiceCapture) -> VoiceTransition:
        admission = self._workflows.admit_voice_capture(
            VoiceCaptureIntent("popup", workflow_id=command.workflow_id)
        )
        if admission.kind not in {"voice_review", "follow_up"} or admission.target is None:
            return VoiceTransition(self._controller.projection, ignored=True)
        return self._controller.request_capture(command.capture_id, admission.target)

    def handle(self, command: OpenVoiceSetup | OpenVoicePermissionSettings | EnableVoiceInput | RetryVoiceInputSetup | DisableVoiceInput | VoiceDisableShutdownCompleted | VoiceDisablePreferenceSaved | VoiceEngineEventReceived | VoicePreferenceSaved | StartPopupVoiceCapture | StopVoiceCapture | CancelVoiceCapture | VoiceCaptureCountdownTick | VoiceCaptureCountdownTickForCapture | VoiceCaptureTimeout | VoiceCaptureWatchdogExpired | VoiceSilenceWatchdogExpired | SetVoiceLanguage | VoiceLanguagePreferenceSaved | UpdateVoiceDraft) -> bool:
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
        elif isinstance(command, VoiceCaptureCountdownTick):
            self._countdown_watchdogs.pop(command.press_id, None)
            transition = self._controller.note_capture_countdown(
                command.press_id,
                command.remaining_seconds,
            )
        elif isinstance(command, VoiceCaptureCountdownTickForCapture):
            self._capture_countdown_watchdogs.pop(command.capture_id, None)
            transition = self._controller.note_capture_countdown_for_capture(
                command.capture_id,
                command.remaining_seconds,
            )
        elif isinstance(command, VoiceCaptureTimeout):
            self._cancel_capture_countdown(command.capture_id)
            transition = self._controller.request_stop(command.capture_id)
        elif isinstance(command, VoiceSilenceWatchdogExpired):
            self._cancel_silence_watchdog(command.capture_id)
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
            if (
                not transition.ignored
                and isinstance(command.event, VoiceEngineListening)
            ):
                press_id = self._controller.press_id_for_capture(command.event.capture_id)
                if press_id is not None and self._start_watchdog(press_id):
                    transition = self._controller.note_capture_countdown(
                        press_id,
                        int(VOICE_CAPTURE_WATCHDOG_SECONDS),
                    )
                elif press_id is None and self._start_capture_watchdog(command.event.capture_id):
                    transition = self._controller.note_capture_countdown_for_capture(
                        command.event.capture_id,
                        int(VOICE_CAPTURE_WATCHDOG_SECONDS),
                    )
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
        if isinstance(command, (DisableVoiceInput, StopVoiceCapture, CancelVoiceCapture, VoiceCaptureTimeout)):
            self._cancel_all_watchdogs()
            self._cancel_all_silence_watchdogs()
        self._execute(transition)
        if (
            isinstance(command, VoiceCaptureCountdownTick)
            and command.remaining_seconds > 0
        ):
            self._schedule_countdown_tick(command.press_id)
        if (
            isinstance(command, VoiceCaptureCountdownTickForCapture)
            and command.remaining_seconds > 0
        ):
            self._schedule_capture_countdown_tick(command.capture_id)
        if isinstance(command, VoiceEngineEventReceived) and isinstance(command.event, VoiceEngineListening):
            self._start_silence_watchdog(command.event.capture_id)
        return True

    def stop(self) -> None:
        self._cancel_all_watchdogs()
        self._cancel_all_silence_watchdogs()
        self._engine.shutdown()

    def _execute(self, transition: VoiceTransition) -> None:
        if transition.projection.capture_id is None:
            self._cancel_all_watchdogs()
            self._cancel_all_silence_watchdogs()
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

    def _start_watchdog(self, press_id: ShortcutPressId) -> bool:
        if press_id in self._watchdogs:
            return False
        self._capture_deadlines[press_id] = (
            self._monotonic_clock() + VOICE_CAPTURE_WATCHDOG_SECONDS
        )
        self._watchdogs[press_id] = self._watchdog_schedule(
            VOICE_CAPTURE_WATCHDOG_SECONDS,
            lambda: self._dispatch_watchdog_expired(press_id),
        )
        self._schedule_countdown_tick(press_id)
        return True

    def _schedule_countdown_tick(self, press_id: ShortcutPressId) -> None:
        deadline = self._capture_deadlines.get(press_id)
        if deadline is None:
            return
        remaining = deadline - self._monotonic_clock()
        if remaining <= 0:
            return
        old_tick = self._countdown_watchdogs.pop(press_id, None)
        if old_tick is not None and hasattr(old_tick, "cancel"):
            old_tick.cancel()
        self._countdown_watchdogs[press_id] = self._watchdog_schedule(
            min(1.0, remaining),
            lambda: self._dispatch_countdown_tick(press_id),
        )

    def _start_capture_watchdog(self, capture_id: VoiceCaptureId) -> bool:
        if capture_id in self._capture_deadlines_by_id:
            return False
        self._capture_deadlines_by_id[capture_id] = self._monotonic_clock() + VOICE_CAPTURE_WATCHDOG_SECONDS
        self._watchdogs[capture_id] = self._watchdog_schedule(
            VOICE_CAPTURE_WATCHDOG_SECONDS,
            lambda: self._dispatch_capture_timeout(capture_id),
        )
        self._schedule_capture_countdown_tick(capture_id)
        return True

    def _schedule_capture_countdown_tick(self, capture_id: VoiceCaptureId) -> None:
        deadline = self._capture_deadlines_by_id.get(capture_id)
        if deadline is None:
            return
        remaining = deadline - self._monotonic_clock()
        if remaining <= 0:
            return
        old_tick = self._capture_countdown_watchdogs.pop(capture_id, None)
        if old_tick is not None and hasattr(old_tick, "cancel"):
            old_tick.cancel()
        self._capture_countdown_watchdogs[capture_id] = self._watchdog_schedule(
            min(1.0, remaining),
            lambda: self._dispatch_capture_countdown_tick(capture_id),
        )

    def _dispatch_capture_countdown_tick(self, capture_id: VoiceCaptureId) -> None:
        deadline = self._capture_deadlines_by_id.get(capture_id)
        if deadline is None:
            return
        remaining_seconds = max(0, math.ceil(deadline - self._monotonic_clock()))
        self._dispatch(VoiceCaptureCountdownTickForCapture(capture_id, remaining_seconds))

    def _dispatch_countdown_tick(self, press_id: ShortcutPressId) -> None:
        deadline = self._capture_deadlines.get(press_id)
        if deadline is None:
            return
        remaining_seconds = max(
            0,
            math.ceil(deadline - self._monotonic_clock()),
        )
        self._dispatch(VoiceCaptureCountdownTick(press_id, remaining_seconds))

    def _dispatch_watchdog_expired(self, press_id: ShortcutPressId) -> None:
        deadline = self._capture_deadlines.get(press_id)
        if deadline is None:
            return
        remaining = deadline - self._monotonic_clock()
        if remaining > 0:
            self._watchdogs[press_id] = self._watchdog_schedule(
                remaining,
                lambda: self._dispatch_watchdog_expired(press_id),
            )
            return
        self._dispatch(VoiceCaptureWatchdogExpired(press_id))

    def _dispatch_capture_timeout(self, capture_id: VoiceCaptureId) -> None:
        deadline = self._capture_deadlines_by_id.get(capture_id)
        if deadline is None:
            return
        remaining = deadline - self._monotonic_clock()
        if remaining > 0:
            self._watchdogs[capture_id] = self._watchdog_schedule(
                remaining,
                lambda: self._dispatch_capture_timeout(capture_id),
            )
            return
        self._dispatch(VoiceCaptureTimeout(capture_id))

    def _cancel_watchdog(self, press_id: ShortcutPressId) -> None:
        watchdog = self._watchdogs.pop(press_id, None)
        if watchdog is not None and hasattr(watchdog, "cancel"):
            watchdog.cancel()
        countdown = self._countdown_watchdogs.pop(press_id, None)
        if countdown is not None and hasattr(countdown, "cancel"):
            countdown.cancel()
        self._capture_deadlines.pop(press_id, None)

    def _cancel_capture_countdown(self, capture_id: VoiceCaptureId) -> None:
        watchdog = self._watchdogs.pop(capture_id, None)
        if watchdog is not None and hasattr(watchdog, "cancel"):
            watchdog.cancel()
        countdown = self._capture_countdown_watchdogs.pop(capture_id, None)
        if countdown is not None and hasattr(countdown, "cancel"):
            countdown.cancel()
        self._capture_deadlines_by_id.pop(capture_id, None)

    def _cancel_all_watchdogs(self) -> None:
        for press_id in tuple(self._watchdogs):
            if press_id in self._capture_deadlines_by_id:
                self._cancel_capture_countdown(press_id)
            else:
                self._cancel_watchdog(press_id)
        for capture_id in tuple(self._capture_deadlines_by_id):
            self._cancel_capture_countdown(capture_id)

    def _start_silence_watchdog(self, capture_id: VoiceCaptureId) -> None:
        self._cancel_silence_watchdog(capture_id)
        self._silence_watchdogs[capture_id] = self._watchdog_schedule(
            VOICE_SILENCE_HINT_SECONDS,
            lambda: self._dispatch(VoiceSilenceWatchdogExpired(capture_id)),
        )

    def _cancel_silence_watchdog(self, capture_id: VoiceCaptureId) -> None:
        watchdog = self._silence_watchdogs.pop(capture_id, None)
        if watchdog is not None and hasattr(watchdog, "cancel"):
            watchdog.cancel()

    def _cancel_all_silence_watchdogs(self) -> None:
        for capture_id in tuple(self._silence_watchdogs):
            self._cancel_silence_watchdog(capture_id)
