from __future__ import annotations

from dataclasses import dataclass

from ClipAI.core.voice import (
    VoiceCaptureId,
    VoiceCapturePhase,
    VoiceCapabilityPhase,
    VoiceDraftTarget,
    VoiceEngineEnded,
    VoiceEngineEvent,
    VoiceEngineFailed,
    VoiceEngineFinalSegment,
    VoiceEngineInterim,
    VoiceEngineListening,
    VoiceEngineSetupBlocked,
    VoiceEngineSetupFailed,
    VoiceEngineSetupReady,
    VoiceLanguage,
    VoiceProjection,
    VoiceSetupId,
    VoiceTransportFailure,
)
from ClipAI.core.models import ShortcutPressId


@dataclass(frozen=True)
class PrepareVoiceSetup:
    setup_id: VoiceSetupId
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


VoiceEffect = PrepareVoiceSetup | StartVoiceCapture | StopVoiceCapture | CancelVoiceCapture | FinalizeVoiceDraft


@dataclass(frozen=True)
class VoiceTransition:
    projection: VoiceProjection
    effects: tuple[VoiceEffect, ...] = ()
    ignored: bool = False


@dataclass
class _Capture:
    capture_id: VoiceCaptureId
    target: VoiceDraftTarget
    press_id: ShortcutPressId | None = None
    phase: VoiceCapturePhase = VoiceCapturePhase.STARTING
    interim_text: str = ""
    next_sequence: int = 0
    segments: dict[int, str] | None = None
    stop_requested: bool = False
    cancelled: bool = False

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
            self._capability = VoiceCapabilityPhase.READY
            self._message = "Voice Input is ready."
        elif isinstance(event, VoiceEngineSetupBlocked):
            self._capability = VoiceCapabilityPhase.PERMISSION_BLOCKED
            self._message = "Microphone permission is blocked."
        else:
            self._capability = VoiceCapabilityPhase.UNAVAILABLE
            self._message = _failure_message(event.failure, event.detail)
        return self._transition()

    def request_capture(
        self,
        capture_id: VoiceCaptureId,
        target: VoiceDraftTarget,
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

    def set_language(self, language: VoiceLanguage) -> VoiceTransition:
        if self._capture is not None or language == self._language:
            return self._ignored()
        self._language = language
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
        if isinstance(event, VoiceEngineFinalSegment):
            return self._observe_final_segment(capture, event)
        if isinstance(event, VoiceEngineEnded):
            return self._settle_ended(capture)
        assert isinstance(event, VoiceEngineFailed)
        return self._settle_failed(capture, event)

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
            return self._transition()
        if not text:
            self._message = "No speech was recognized. Try again."
            return self._transition()
        self._message = warning or "Review your dictation."
        return self._transition(FinalizeVoiceDraft(capture_id, target, text, warning))

    def _settle_failed(self, capture: _Capture, event: VoiceEngineFailed) -> VoiceTransition:
        self._capture = None
        self._message = _failure_message(event.failure, event.detail)
        return self._transition()

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
