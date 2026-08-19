from __future__ import annotations

from dataclasses import dataclass

from ClipAI.core.voice import (
    VoiceCaptureId,
    VoiceCaptureDestination,
    VoiceCaptureTarget,
    VoiceDisableId,
    VoiceCapturePhase,
    VoiceCapabilityPhase,
    VoiceDraftTarget,
    VoiceEngineAudioLevel,
    VoiceEngineEnded,
    VoiceEngineEvent,
    VoiceEngineFailed,
    VoiceEngineFinalSegment,
    VoiceEngineInterim,
    VoiceEngineListening,
    VoiceEngineSetupBlocked,
    VoiceEngineSetupFailed,
    VoiceEngineSetupReady,
    VoiceFollowUpTarget,
    VoiceLanguage,
    VoiceLanguageChangeId,
    VoiceProjection,
    VoiceSetupId,
    VoiceTransportFailure,
)
from ClipAI.core.models import ShortcutPressId


_UNSET_DISABLE_RESULT = object()


@dataclass(frozen=True)
class PrepareVoiceSetup:
    setup_id: VoiceSetupId
    language: VoiceLanguage


@dataclass(frozen=True)
class PersistVoiceEnabled:
    setup_id: VoiceSetupId


@dataclass(frozen=True)
class ShutdownVoiceEngine:
    disable_id: VoiceDisableId


@dataclass(frozen=True)
class PersistVoiceDisabled:
    disable_id: VoiceDisableId


@dataclass(frozen=True)
class PersistVoiceLanguage:
    operation_id: VoiceLanguageChangeId
    language: VoiceLanguage


@dataclass(frozen=True)
class StartVoiceCapture:
    capture_id: VoiceCaptureId
    language: VoiceLanguage
    sequence_start: int = 0


@dataclass(frozen=True)
class StopVoiceCapture:
    capture_id: VoiceCaptureId


@dataclass(frozen=True)
class CancelVoiceCapture:
    capture_id: VoiceCaptureId


@dataclass(frozen=True)
class FinalizeVoiceDraft:
    capture_id: VoiceCaptureId
    target: VoiceDraftTarget
    text: str
    warning: str = ""


@dataclass(frozen=True)
class FinalizeVoiceFollowUp:
    capture_id: VoiceCaptureId
    target: VoiceFollowUpTarget
    text: str
    warning: str = ""


@dataclass(frozen=True)
class RestoreVoiceReview:
    target: VoiceDraftTarget
    message: str


@dataclass(frozen=True)
class RestoreVoiceFollowUp:
    target: VoiceFollowUpTarget
    message: str


VoiceEffect = PrepareVoiceSetup | PersistVoiceEnabled | ShutdownVoiceEngine | PersistVoiceDisabled | PersistVoiceLanguage | StartVoiceCapture | StopVoiceCapture | CancelVoiceCapture | FinalizeVoiceDraft | FinalizeVoiceFollowUp | RestoreVoiceReview | RestoreVoiceFollowUp


@dataclass(frozen=True)
class VoiceTransition:
    projection: VoiceProjection
    effects: tuple[VoiceEffect, ...] = ()
    ignored: bool = False


@dataclass
class _Capture:
    capture_id: VoiceCaptureId
    target: VoiceCaptureTarget
    press_id: ShortcutPressId | None = None
    phase: VoiceCapturePhase = VoiceCapturePhase.STARTING
    interim_text: str = ""
    next_sequence: int = 0
    segments: dict[int, str] | None = None
    stop_requested: bool = False
    cancelled: bool = False
    audio_level: float = 0.0
    heard_audio: bool = False
    silence_detected: bool = False

    def __post_init__(self) -> None:
        if self.segments is None:
            self.segments = {}


class VoiceInputController:
    """Single owner of Voice capability, capture, provisional text, and settlement."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        language: VoiceLanguage = VoiceLanguage("zh-TW"),
    ) -> None:
        self._capability = VoiceCapabilityPhase.READY if enabled else VoiceCapabilityPhase.SETUP_REQUIRED
        self._language = language
        self._setup_id: VoiceSetupId | None = None
        self._pending_enable_save: VoiceSetupId | None = None
        self._disable_id: VoiceDisableId | None = None
        self._disable_shutdown_result: str | object = _UNSET_DISABLE_RESULT
        self._disable_preference_result: str | object = _UNSET_DISABLE_RESULT
        self._pending_language: tuple[VoiceLanguageChangeId, VoiceLanguage] | None = None
        self._capture: _Capture | None = None
        self._message = ""

    @property
    def projection(self) -> VoiceProjection:
        capture = self._capture
        return VoiceProjection(
            self._capability,
            self._language,
            capture.capture_id if capture is not None else None,
            capture.phase if capture is not None else None,
            capture.interim_text if capture is not None else "",
            self._message,
            capture.target.workflow_id if capture is not None else None,
            capture.audio_level if capture is not None else 0.0,
            capture.silence_detected if capture is not None else False,
            (
                VoiceCaptureDestination.FOLLOW_UP
                if capture is not None and isinstance(capture.target, VoiceFollowUpTarget)
                else VoiceCaptureDestination.VOICE_DRAFT if capture is not None else None
            ),
        )

    def request_setup(self, setup_id: VoiceSetupId) -> VoiceTransition:
        if self._capability not in {VoiceCapabilityPhase.SETUP_REQUIRED, VoiceCapabilityPhase.UNAVAILABLE, VoiceCapabilityPhase.PERMISSION_BLOCKED} or self._setup_id is not None:
            return self._ignored()
        self._setup_id = setup_id
        self._capability = VoiceCapabilityPhase.REQUESTING_PERMISSION
        self._message = "Preparing Voice Input…"
        return self._transition(PrepareVoiceSetup(setup_id, self._language))

    def complete_setup(self, event: VoiceEngineSetupReady | VoiceEngineSetupBlocked | VoiceEngineSetupFailed) -> VoiceTransition:
        if event.setup_id != self._setup_id:
            return self._ignored()
        self._setup_id = None
        if isinstance(event, VoiceEngineSetupReady):
            self._pending_enable_save = event.setup_id
            self._message = "Saving Voice Input preference…"
            return self._transition(PersistVoiceEnabled(event.setup_id))
        elif isinstance(event, VoiceEngineSetupBlocked):
            self._capability = VoiceCapabilityPhase.PERMISSION_BLOCKED
            self._message = "Microphone permission is blocked."
        else:
            self._capability = VoiceCapabilityPhase.UNAVAILABLE
            self._message = _failure_message(event.failure, event.detail)
        return self._transition()

    def complete_enable_save(self, setup_id: VoiceSetupId, error: str = "") -> VoiceTransition:
        if self._pending_enable_save != setup_id:
            return self._ignored()
        self._pending_enable_save = None
        if error:
            self._capability = VoiceCapabilityPhase.SETUP_REQUIRED
            self._message = "Voice Input permission is ready, but the setting could not be saved. Try again."
        else:
            self._capability = VoiceCapabilityPhase.READY
            self._message = "Voice Input is ready."
        return self._transition()

    def request_disable(self, disable_id: VoiceDisableId) -> VoiceTransition:
        if self._disable_id is not None or self._capability is VoiceCapabilityPhase.DISABLED:
            return self._ignored()
        self._disable_id = disable_id
        self._setup_id = None
        self._pending_enable_save = None
        self._disable_shutdown_result = _UNSET_DISABLE_RESULT
        self._disable_preference_result = _UNSET_DISABLE_RESULT
        self._capability = VoiceCapabilityPhase.DISABLING
        self._message = "Disabling Voice Input…"
        effects: list[VoiceEffect] = [ShutdownVoiceEngine(disable_id), PersistVoiceDisabled(disable_id)]
        if self._capture is not None:
            effects.insert(0, CancelVoiceCapture(self._capture.capture_id))
        return self._transition(*effects)

    def complete_disable_shutdown(self, disable_id: VoiceDisableId, error: str = "") -> VoiceTransition:
        if disable_id != self._disable_id or self._disable_shutdown_result is not _UNSET_DISABLE_RESULT:
            return self._ignored()
        self._disable_shutdown_result = error
        return self._settle_disable()

    def complete_disable_preference(self, disable_id: VoiceDisableId, error: str = "") -> VoiceTransition:
        if disable_id != self._disable_id or self._disable_preference_result is not _UNSET_DISABLE_RESULT:
            return self._ignored()
        self._disable_preference_result = error
        return self._settle_disable()

    def _settle_disable(self) -> VoiceTransition:
        if (
            self._disable_shutdown_result is _UNSET_DISABLE_RESULT
            or self._disable_preference_result is _UNSET_DISABLE_RESULT
        ):
            return self._transition()
        shutdown_error = self._disable_shutdown_result
        preference_error = self._disable_preference_result
        assert isinstance(shutdown_error, str)
        assert isinstance(preference_error, str)
        self._disable_id = None
        self._disable_shutdown_result = _UNSET_DISABLE_RESULT
        self._disable_preference_result = _UNSET_DISABLE_RESULT
        if shutdown_error:
            self._capability = VoiceCapabilityPhase.CLEANUP_UNCONFIRMED
            self._message = "Voice Input disabled, but microphone cleanup could not be confirmed."
        elif preference_error:
            self._capability = VoiceCapabilityPhase.DISABLE_FAILED
            self._message = "Voice Input stopped, but the disabled setting could not be saved."
        else:
            self._capability = VoiceCapabilityPhase.DISABLED
            self._message = "Voice Input disabled."
        return self._transition()

    def request_capture(
        self,
        capture_id: VoiceCaptureId,
        target: VoiceCaptureTarget,
        *,
        press_id: ShortcutPressId | None = None,
    ) -> VoiceTransition:
        if self._capability is not VoiceCapabilityPhase.READY or self._capture is not None:
            return self._ignored()
        self._capture = _Capture(capture_id, target, press_id)
        self._message = "Preparing microphone…"
        return self._transition(StartVoiceCapture(capture_id, self._language))

    def request_capture_for_press(self, press_id: ShortcutPressId, target: VoiceDraftTarget) -> VoiceTransition:
        """Accept a physical PTT press without leaking press ownership to runtime."""
        return self.request_capture(VoiceCaptureId(f"voice-press-{press_id}"), target, press_id=press_id)

    def set_language(self, language: VoiceLanguage, operation_id: VoiceLanguageChangeId) -> VoiceTransition:
        if self._capture is not None or self._pending_language is not None or language == self._language:
            return self._ignored()
        self._pending_language = (operation_id, language)
        self._message = "Saving Voice Input language…"
        return self._transition(PersistVoiceLanguage(operation_id, language))

    def complete_language_save(self, operation_id: VoiceLanguageChangeId, error: str = "") -> VoiceTransition:
        pending = self._pending_language
        if pending is None or pending[0] != operation_id:
            return self._ignored()
        self._pending_language = None
        if error:
            self._message = "Voice Input language could not be saved."
        else:
            self._language = pending[1]
            self._message = "Voice Input language updated."
        return self._transition()

    def request_release_for_press(self, press_id: ShortcutPressId) -> VoiceTransition:
        capture = self._capture
        if capture is None or capture.press_id != press_id:
            return self._ignored()
        return self.request_stop(capture.capture_id)

    def abandon_press(self, press_id: ShortcutPressId) -> VoiceTransition:
        capture = self._capture
        if capture is None or capture.press_id != press_id:
            return self._ignored()
        return self.request_cancel(capture.capture_id)

    def expire_capture_watchdog(self, press_id: ShortcutPressId) -> VoiceTransition:
        """Cancel only the capture still bound to the missing terminal press."""
        capture = self._capture
        if capture is None or capture.press_id != press_id or capture.stop_requested:
            return self._ignored()
        transition = self.request_cancel(capture.capture_id)
        self._message = "Voice Input cancelled because the shortcut release was not received."
        return self._transition(*transition.effects)

    def cancel_capture_for_workflow(self, workflow_id: str) -> VoiceTransition:
        capture = self._capture
        if capture is None or capture.target.workflow_id != workflow_id:
            return self._ignored()
        return self.request_cancel(capture.capture_id)

    def request_stop(self, capture_id: VoiceCaptureId) -> VoiceTransition:
        capture = self._matching_capture(capture_id)
        if capture is None or capture.stop_requested:
            return self._ignored()
        capture.stop_requested = True
        capture.phase = VoiceCapturePhase.FINALIZING
        self._message = "Finalizing…"
        return self._transition(StopVoiceCapture(capture_id))

    def request_cancel(self, capture_id: VoiceCaptureId) -> VoiceTransition:
        capture = self._matching_capture(capture_id)
        if capture is None or capture.cancelled:
            return self._ignored()
        capture.cancelled = True
        capture.stop_requested = True
        capture.phase = VoiceCapturePhase.CANCEL_REQUESTED
        self._message = "Cancelling Voice Input…"
        return self._transition(CancelVoiceCapture(capture_id))

    def observe_engine(self, event: VoiceEngineEvent) -> VoiceTransition:
        if isinstance(event, (VoiceEngineSetupReady, VoiceEngineSetupBlocked, VoiceEngineSetupFailed)):
            return self.complete_setup(event)
        capture = self._matching_capture(event.capture_id)
        if capture is None:
            return self._ignored()
        if isinstance(event, VoiceEngineListening):
            if capture.stop_requested:
                return self._ignored()
            capture.phase = VoiceCapturePhase.LISTENING
            self._message = "Listening…"
            return self._transition()
        if isinstance(event, VoiceEngineInterim):
            if capture.stop_requested:
                return self._ignored()
            capture.interim_text = event.text
            return self._transition()
        if isinstance(event, VoiceEngineAudioLevel):
            if capture.stop_requested:
                return self._ignored()
            capture.audio_level = event.level
            if event.level > 0.02:
                capture.heard_audio = True
                capture.silence_detected = False
                self._message = "Listening…"
            return self._transition()
        if isinstance(event, VoiceEngineFinalSegment):
            return self._observe_final_segment(capture, event)
        if isinstance(event, VoiceEngineEnded):
            return self._settle_ended(capture)
        assert isinstance(event, VoiceEngineFailed)
        return self._settle_failed(capture, event)

    def note_silence_timeout(self, capture_id: VoiceCaptureId) -> VoiceTransition:
        """Project a non-terminal no-signal hint for the matching capture."""
        capture = self._matching_capture(capture_id)
        if capture is None or capture.stop_requested or capture.heard_audio:
            return self._ignored()
        capture.silence_detected = True
        self._message = "No sound detected."
        return self._transition()

    def _observe_final_segment(self, capture: _Capture, event: VoiceEngineFinalSegment) -> VoiceTransition:
        assert capture.segments is not None
        prior = capture.segments.get(event.sequence)
        if prior is not None:
            if prior == event.text:
                return self._ignored()
            return self._settle_failed(capture, VoiceEngineFailed(event.capture_id, VoiceTransportFailure.PROTOCOL_ERROR))
        if event.sequence < capture.next_sequence:
            return self._ignored()
        capture.segments[event.sequence] = event.text
        while capture.next_sequence in capture.segments:
            capture.next_sequence += 1
        return self._transition()

    def _settle_ended(self, capture: _Capture) -> VoiceTransition:
        assert capture.segments is not None
        if not capture.stop_requested:
            if capture.phase is VoiceCapturePhase.STARTING and not capture.segments:
                target = capture.target
                self._capture = None
                self._message = "Voice Input stopped before the microphone was ready. Try again."
                return self._transition(self._restore_effect(target, self._message))
            capture.phase = VoiceCapturePhase.STARTING
            capture.interim_text = ""
            self._message = "Listening…"
            return self._transition(StartVoiceCapture(capture.capture_id, self._language, capture.next_sequence))
        text_parts = [capture.segments[sequence] for sequence in range(capture.next_sequence)]
        warning = (
            "Recognition completed with a missing segment."
            if any(sequence > capture.next_sequence for sequence in capture.segments)
            else ""
        )
        text = " ".join(part.strip() for part in text_parts if part.strip())
        capture_id, target, cancelled = capture.capture_id, capture.target, capture.cancelled
        self._capture = None
        if cancelled:
            self._message = "Voice Input cancelled."
            return self._transition(self._restore_effect(target, self._message))
        if not text:
            self._message = "No speech was recognized. Try again."
            return self._transition(self._restore_effect(target, self._message))
        self._message = warning or "Review your dictation."
        return self._transition(self._finalize_effect(capture_id, target, text, warning))

    def _settle_failed(self, capture: _Capture, event: VoiceEngineFailed) -> VoiceTransition:
        target = capture.target
        self._capture = None
        if event.failure in {
            VoiceTransportFailure.PERMISSION_DENIED,
            VoiceTransportFailure.PERMISSION_BLOCKED,
        }:
            self._capability = VoiceCapabilityPhase.PERMISSION_BLOCKED
        self._message = _failure_message(event.failure, event.detail)
        return self._transition(self._restore_effect(target, self._message))

    @staticmethod
    def _restore_effect(target: VoiceCaptureTarget, message: str) -> VoiceEffect:
        return (
            RestoreVoiceFollowUp(target, message)
            if isinstance(target, VoiceFollowUpTarget)
            else RestoreVoiceReview(target, message)
        )

    @staticmethod
    def _finalize_effect(
        capture_id: VoiceCaptureId,
        target: VoiceCaptureTarget,
        text: str,
        warning: str,
    ) -> VoiceEffect:
        return (
            FinalizeVoiceFollowUp(capture_id, target, text, warning)
            if isinstance(target, VoiceFollowUpTarget)
            else FinalizeVoiceDraft(capture_id, target, text, warning)
        )

    def _matching_capture(self, capture_id: VoiceCaptureId) -> _Capture | None:
        capture = self._capture
        return capture if capture is not None and capture.capture_id == capture_id else None

    def _transition(self, *effects: VoiceEffect) -> VoiceTransition:
        return VoiceTransition(self.projection, effects)

    def _ignored(self) -> VoiceTransition:
        return VoiceTransition(self.projection, ignored=True)


def _failure_message(failure: VoiceTransportFailure, detail: str) -> str:
    messages = {
        VoiceTransportFailure.PERMISSION_DENIED: "Microphone permission was denied.",
        VoiceTransportFailure.PERMISSION_BLOCKED: "Microphone permission is blocked.",
        VoiceTransportFailure.UNAVAILABLE: "Voice Input is unavailable on this device.",
        VoiceTransportFailure.INITIALIZATION_FAILED: "Voice Input could not start.",
        VoiceTransportFailure.PROCESS_CRASHED: "Voice Input stopped unexpectedly. Try again.",
        VoiceTransportFailure.PROTOCOL_ERROR: "Voice Input received an invalid recognition response.",
        VoiceTransportFailure.TIMEOUT: "Voice Input timed out. Try again.",
        VoiceTransportFailure.CANCELLED: "Voice Input cancelled.",
    }
    return detail or messages[failure]
