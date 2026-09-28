from __future__ import annotations

from dataclasses import dataclass, replace
import uuid

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
    VoiceInlineTarget,
    VoiceLanguage,
    VoiceLanguageChangeId,
    VoiceProjection,
    VoiceSetupId,
    VoiceTransportFailure,
)
from ClipAI.core.models import PasteOutcome, PasteTarget, ShortcutPressId


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
    capture_id: VoiceCaptureId
    target: VoiceFollowUpTarget
    message: str


@dataclass(frozen=True)
class PresentInlineChoice:
    interaction_id: str
    text: str
    allow_refine: bool = True
    message: str = ""


@dataclass(frozen=True)
class PasteInlineDictation:
    text: str
    target: PasteTarget
    refine: bool = False
    interaction_id: str = ""
    operation_id: str = ""


@dataclass(frozen=True)
class DiscardInlineDictation:
    interaction_id: str
    message: str = ""


@dataclass(frozen=True)
class CancelInlinePaste:
    operation_id: str
    interaction_id: str = ""


@dataclass(frozen=True)
class CancelInlineRefinement:
    interaction_id: str
    operation_id: str


@dataclass(frozen=True)
class PresentInlinePasteOutcome:
    interaction_id: str
    outcome: PasteOutcome
    text: str


@dataclass(frozen=True)
class PresentInlineRecovery:
    interaction_id: str
    text: str
    message: str


@dataclass(frozen=True)
class PresentInlineCancelUnconfirmed:
    interaction_id: str
    text: str


@dataclass(frozen=True)
class CopyInlineText:
    interaction_id: str
    operation_id: str
    text: str


@dataclass(frozen=True)
class PresentInlineCopyState:
    interaction_id: str
    state: str


@dataclass(frozen=True)
class CloseInlineTerminal:
    interaction_id: str


VoiceEffect = PrepareVoiceSetup | PersistVoiceEnabled | ShutdownVoiceEngine | PersistVoiceDisabled | PersistVoiceLanguage | StartVoiceCapture | StopVoiceCapture | CancelVoiceCapture | FinalizeVoiceDraft | FinalizeVoiceFollowUp | RestoreVoiceReview | RestoreVoiceFollowUp | PresentInlineChoice | PasteInlineDictation | DiscardInlineDictation | CancelInlinePaste | CancelInlineRefinement | PresentInlinePasteOutcome | PresentInlineRecovery | PresentInlineCancelUnconfirmed | CopyInlineText | PresentInlineCopyState | CloseInlineTerminal


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
    remaining_seconds: int | None = None
    safety_limit_reached: bool = False
    progress_since_restart: bool = False
    restarts_without_progress: int = 0
    inline_delivery: bool | None = None

    def __post_init__(self) -> None:
        if self.segments is None:
            self.segments = {}


@dataclass(frozen=True)
class _PendingInline:
    text: str
    target: VoiceInlineTarget
    delivery_text: str = ""
    refine_failed: bool = False
    refining: bool = False
    refine_operation_id: str | None = None
    paste_operation_id: str | None = None
    discard_requested: bool = False
    cancel_timed_out: bool = False
    paste_outcome: PasteOutcome | None = None
    recovery_message: str = ""
    copy_operation_id: str | None = None


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
        self._pending_inline: _PendingInline | None = None
        self._awaiting_release_press_id: ShortcutPressId | None = None
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
            capture.target.workflow_id if capture is not None and not isinstance(capture.target, VoiceInlineTarget) else None,
            capture.audio_level if capture is not None else 0.0,
            capture.silence_detected if capture is not None else False,
            (
                VoiceCaptureDestination.FOLLOW_UP
                if capture is not None and isinstance(capture.target, VoiceFollowUpTarget)
                else VoiceCaptureDestination.INLINE
                if capture is not None and isinstance(capture.target, VoiceInlineTarget)
                else VoiceCaptureDestination.VOICE_DRAFT if capture is not None else None
            ),
            capture.remaining_seconds if capture is not None else None,
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
            self._capture.cancelled = True
            self._capture.stop_requested = True
            self._capture.phase = VoiceCapturePhase.CANCEL_REQUESTED
            effects.insert(0, CancelVoiceCapture(self._capture.capture_id))
        if self._pending_inline is not None:
            pending = self._pending_inline
            self._pending_inline = None
            if pending.refine_operation_id is not None:
                effects.insert(0, CancelInlineRefinement(pending.target.interaction_id, pending.refine_operation_id))
            if pending.paste_operation_id is not None and pending.paste_outcome is None:
                effects.insert(0, CancelInlinePaste(pending.paste_operation_id, pending.target.interaction_id))
            effects.append(DiscardInlineDictation(pending.target.interaction_id))
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
        if self._capability is not VoiceCapabilityPhase.READY or self._capture is not None or self._pending_inline is not None:
            return self._ignored()
        self._capture = _Capture(capture_id, target, press_id)
        self._message = "Preparing microphone…"
        return self._transition(StartVoiceCapture(capture_id, self._language))

    def request_capture_for_press(self, press_id: ShortcutPressId, target: VoiceCaptureTarget) -> VoiceTransition:
        """Accept a physical PTT press without leaking press ownership to runtime."""
        if self._awaiting_release_press_id is not None:
            return self._ignored()
        return self.request_capture(VoiceCaptureId(f"voice-press-{press_id}"), target, press_id=press_id)

    def press_id_for_capture(self, capture_id: VoiceCaptureId) -> ShortcutPressId | None:
        capture = self._matching_capture(capture_id)
        return capture.press_id if capture is not None else None

    def active_inline_capture_id(self) -> VoiceCaptureId | None:
        capture = self._capture
        return capture.capture_id if capture is not None and isinstance(capture.target, VoiceInlineTarget) else None

    def active_inline_interaction_id(self) -> str | None:
        capture = self._capture
        if capture is not None and isinstance(capture.target, VoiceInlineTarget):
            return capture.target.interaction_id
        return self.inline_interaction_id()

    def has_pending_inline_choice(self) -> bool:
        return self._pending_inline is not None

    def confirm_inline_settlement(self, interaction_id: str, refine: bool = False) -> VoiceTransition:
        pending = self._pending_inline
        if pending is None or pending.target.interaction_id != interaction_id or pending.target.paste_target is None or pending.refining or pending.paste_operation_id is not None or pending.paste_outcome is not None or pending.recovery_message or (refine and pending.refine_failed):
            return self._ignored()
        if refine:
            operation_id = f"inline-refine-{uuid.uuid4().hex}"
            self._pending_inline = replace(pending, refining=True, refine_operation_id=operation_id)
            self._message = "Refining dictation…"
        else:
            operation_id = f"inline-paste-{uuid.uuid4().hex}"
            self._pending_inline = replace(pending, paste_operation_id=operation_id)
        return self._transition(PasteInlineDictation(pending.text, pending.target.paste_target, refine, pending.target.interaction_id, operation_id))

    def complete_inline_refinement(self, interaction_id: str, operation_id: str, text: str = "", *, error: bool = False) -> VoiceTransition:
        pending = self._pending_inline
        if pending is None or not pending.refining or pending.target.interaction_id != interaction_id or pending.refine_operation_id != operation_id:
            return self._ignored()
        if pending.discard_requested:
            self._pending_inline = None
            return self._transition(DiscardInlineDictation(interaction_id))
        if error or not text.strip():
            self._pending_inline = replace(pending, refining=False, refine_operation_id=None, refine_failed=True)
            self._message = "Dictation could not be refined. Choose raw paste or discard."
            return self._transition(PresentInlineChoice(interaction_id, pending.text, allow_refine=False, message=self._message))
        paste_operation_id = f"inline-paste-{uuid.uuid4().hex}"
        self._pending_inline = replace(pending, refining=False, refine_operation_id=None, paste_operation_id=paste_operation_id, delivery_text=text)
        assert pending.target.paste_target is not None
        self._message = "Preparing paste…"
        return self._transition(PasteInlineDictation(text, pending.target.paste_target, False, interaction_id, paste_operation_id))

    def accept_inline_refinement_cancellation(self, interaction_id: str, operation_id: str, accepted: bool) -> VoiceTransition:
        pending = self._pending_inline
        if pending is None or pending.target.interaction_id != interaction_id or pending.refine_operation_id != operation_id or not pending.discard_requested:
            return self._ignored()
        if not accepted:
            self._message = "Waiting for refinement to settle before cancelling…"
            return self._transition()
        self._pending_inline = None
        return self._transition(DiscardInlineDictation(interaction_id))

    def note_inline_refinement_cancel_timeout(self, interaction_id: str, operation_id: str) -> VoiceTransition:
        pending = self._pending_inline
        if (
            pending is None or pending.target.interaction_id != interaction_id
            or pending.refine_operation_id != operation_id or not pending.discard_requested
            or pending.cancel_timed_out
        ):
            return self._ignored()
        self._pending_inline = replace(pending, cancel_timed_out=True)
        self._message = "Cancellation is unconfirmed. No paste will be requested; the original text remains available to copy."
        return self._transition(PresentInlineCancelUnconfirmed(interaction_id, pending.text))

    def inline_paste_operation_id(self, interaction_id: str) -> str | None:
        pending = self._pending_inline
        if pending is None or pending.target.interaction_id != interaction_id:
            return None
        return pending.paste_operation_id

    def inline_interaction_id(self) -> str | None:
        pending = self._pending_inline
        return pending.target.interaction_id if pending is not None else None

    def dismiss_inline_terminal(self, interaction_id: str) -> VoiceTransition:
        pending = self._pending_inline
        if (
            pending is None
            or pending.target.interaction_id != interaction_id
            or pending.paste_outcome is None
            or pending.paste_outcome.state not in {"dispatched_unconfirmed", "cancelled"}
        ):
            return self._ignored()
        self._pending_inline = None
        return self._transition(CloseInlineTerminal(interaction_id))

    def request_inline_copy(self, interaction_id: str) -> VoiceTransition:
        pending = self._pending_inline
        if (
            pending is None
            or pending.target.interaction_id != interaction_id
            or pending.copy_operation_id is not None
            or (pending.refining and not pending.cancel_timed_out)
            or (pending.paste_operation_id is not None and pending.paste_outcome is None)
        ):
            return self._ignored()
        operation_id = f"inline-copy-{uuid.uuid4().hex}"
        self._pending_inline = replace(pending, copy_operation_id=operation_id)
        return self._transition(PresentInlineCopyState(interaction_id, "pending"), CopyInlineText(interaction_id, operation_id, pending.delivery_text or pending.text))

    def complete_inline_copy(self, interaction_id: str, operation_id: str, error: str = "") -> VoiceTransition:
        pending = self._pending_inline
        if pending is None or pending.target.interaction_id != interaction_id or pending.copy_operation_id != operation_id:
            return self._ignored()
        self._pending_inline = replace(pending, copy_operation_id=None)
        return self._transition(PresentInlineCopyState(interaction_id, "failed" if error else "succeeded"))

    def complete_inline_paste(self, interaction_id: str, operation_id: str, outcome: PasteOutcome) -> VoiceTransition:
        pending = self._pending_inline
        if pending is None or pending.target.interaction_id != interaction_id or pending.paste_operation_id != operation_id or pending.paste_outcome is not None:
            return self._ignored()
        self._pending_inline = replace(pending, paste_outcome=outcome)
        self._message = _inline_paste_message(outcome)
        return self._transition(PresentInlinePasteOutcome(interaction_id, outcome, pending.delivery_text or pending.text))

    def cancel_inline(self, interaction_id: str | None = None) -> VoiceTransition:
        if interaction_id is not None and self.active_inline_interaction_id() != interaction_id:
            return self._ignored()
        if self._pending_inline is not None:
            pending = self._pending_inline
            if pending.refining and pending.refine_operation_id is not None:
                if pending.discard_requested:
                    if pending.cancel_timed_out:
                        self._pending_inline = replace(pending, cancel_timed_out=False)
                        self._message = "Retrying cancellation…"
                        return self._transition(CancelInlineRefinement(pending.target.interaction_id, pending.refine_operation_id))
                    return self._ignored()
                self._pending_inline = replace(pending, discard_requested=True)
                self._message = "Cancelling refinement…"
                return self._transition(CancelInlineRefinement(pending.target.interaction_id, pending.refine_operation_id))
            if pending.paste_operation_id is not None and pending.paste_outcome is None:
                if pending.discard_requested:
                    return self._ignored()
                self._pending_inline = replace(pending, discard_requested=True)
                self._message = "Cancelling paste…"
                return self._transition(CancelInlinePaste(pending.paste_operation_id, pending.target.interaction_id))
            self._pending_inline = None
            return self._transition(DiscardInlineDictation(pending.target.interaction_id))
        capture_id = self.active_inline_capture_id()
        if capture_id is not None:
            return self.request_cancel(capture_id)
        return self._ignored()

    def force_settle_pending_stop(self, capture_id: VoiceCaptureId) -> VoiceTransition:
        capture = self._matching_capture(capture_id)
        if capture is None or not capture.stop_requested:
            return self._ignored()
        return self._settle_stop(capture, timed_out=True)

    def note_capture_countdown(
        self,
        press_id: ShortcutPressId,
        remaining_seconds: int,
    ) -> VoiceTransition:
        capture = self._capture
        if (
            capture is None
            or capture.press_id != press_id
            or capture.stop_requested
            or remaining_seconds < 0
        ):
            return self._ignored()
        capture.remaining_seconds = remaining_seconds
        self._message = self._listening_message(capture)
        return self._transition()

    def note_capture_countdown_for_capture(
        self,
        capture_id: VoiceCaptureId,
        remaining_seconds: int,
    ) -> VoiceTransition:
        capture = self._matching_capture(capture_id)
        if capture is None or capture.stop_requested or remaining_seconds < 0:
            return self._ignored()
        capture.remaining_seconds = remaining_seconds
        self._message = self._listening_message(capture)
        return self._transition()

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
        if self._awaiting_release_press_id == press_id:
            self._awaiting_release_press_id = None
            capture = self._capture
            if capture is None or capture.press_id != press_id or capture.stop_requested:
                return self._transition()
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
        """Gracefully stop the PTT capture at its safety limit and require release."""
        capture = self._capture
        if capture is None or capture.press_id != press_id or capture.stop_requested:
            return self._ignored()
        capture.safety_limit_reached = True
        self._awaiting_release_press_id = press_id
        transition = self.request_stop(capture.capture_id)
        self._message = "Voice Input time limit reached. Saving this section…"
        return self._transition(*transition.effects)

    def cancel_capture_for_workflow(self, workflow_id: str) -> VoiceTransition:
        capture = self._capture
        if capture is None or isinstance(capture.target, VoiceInlineTarget) or capture.target.workflow_id != workflow_id:
            return self._ignored()
        return self.request_cancel(capture.capture_id)

    def request_stop(self, capture_id: VoiceCaptureId, *, inline_delivery: bool | None = None) -> VoiceTransition:
        capture = self._matching_capture(capture_id)
        if capture is None or capture.stop_requested:
            return self._ignored()
        capture.stop_requested = True
        if isinstance(capture.target, VoiceInlineTarget):
            capture.inline_delivery = inline_delivery
        capture.phase = VoiceCapturePhase.FINALIZING
        capture.remaining_seconds = None
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
            self._message = self._listening_message(capture)
            return self._transition()
        if isinstance(event, VoiceEngineInterim):
            if capture.stop_requested:
                return self._ignored()
            capture.interim_text = event.text
            if event.text.strip():
                capture.progress_since_restart = True
            return self._transition()
        if isinstance(event, VoiceEngineAudioLevel):
            if capture.stop_requested:
                return self._ignored()
            capture.audio_level = event.level
            if event.level > 0.02:
                capture.heard_audio = True
                capture.progress_since_restart = True
                capture.silence_detected = False
                self._message = self._listening_message(capture)
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
        if event.text.strip():
            capture.progress_since_restart = True
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
                return self._transition(self._restore_effect(capture.capture_id, target, self._message))
            if capture.progress_since_restart:
                capture.restarts_without_progress = 0
            else:
                capture.restarts_without_progress += 1
            if capture.restarts_without_progress >= 3:
                capture.stop_requested = True
                return self._settle_stop(capture)
            capture.progress_since_restart = False
            capture.phase = VoiceCapturePhase.STARTING
            capture.interim_text = ""
            self._message = self._listening_message(capture)
            return self._transition(StartVoiceCapture(capture.capture_id, self._language, capture.next_sequence))
        return self._settle_stop(capture)

    def _settle_stop(self, capture: _Capture, *, timed_out: bool = False) -> VoiceTransition:
        assert capture.segments is not None
        text_parts = [capture.segments[sequence] for sequence in range(capture.next_sequence)]
        warning = (
            "Recognition completed with a missing segment."
            if any(sequence > capture.next_sequence for sequence in capture.segments)
            else ""
        )
        if capture.safety_limit_reached:
            warning = "The 2-minute Voice Input limit was reached. This section was saved; release the shortcut and press it again to continue."
        if timed_out:
            warning = "Voice Input timed out while finalizing. Try again."
        text = " ".join(part.strip() for part in text_parts if part.strip())
        capture_id, target, cancelled = capture.capture_id, capture.target, capture.cancelled
        inline_delivery = capture.inline_delivery
        self._capture = None
        if cancelled:
            self._message = "Voice Input cancellation timed out." if timed_out else "Voice Input cancelled."
            effect_message = self._message if timed_out or not isinstance(target, VoiceInlineTarget) else ""
            return self._transition(self._restore_effect(capture_id, target, effect_message))
        if not text:
            self._message = warning or "No speech was recognized. Try again."
            return self._transition(self._restore_effect(capture_id, target, self._message))
        self._message = warning or "Review your dictation."
        return self._transition(self._finalize_effect(capture_id, target, text, warning, inline_delivery=inline_delivery))

    def _settle_failed(self, capture: _Capture, event: VoiceEngineFailed) -> VoiceTransition:
        target = capture.target
        self._capture = None
        if event.failure in {
            VoiceTransportFailure.PERMISSION_DENIED,
            VoiceTransportFailure.PERMISSION_BLOCKED,
        }:
            self._capability = VoiceCapabilityPhase.PERMISSION_BLOCKED
        self._message = _failure_message(event.failure, event.detail)
        if capture.cancelled:
            return self._transition(self._restore_effect(event.capture_id, target, self._message))
        assert capture.segments is not None
        text = " ".join(
            capture.segments[sequence].strip()
            for sequence in range(capture.next_sequence)
            if capture.segments[sequence].strip()
        )
        if text:
            self._message = f"{self._message} Recognized content was preserved."
            return self._transition(
                self._finalize_effect(event.capture_id, target, text, self._message)
            )
        return self._transition(self._restore_effect(event.capture_id, target, self._message))

    def _restore_effect(
        self,
        capture_id: VoiceCaptureId,
        target: VoiceCaptureTarget,
        message: str,
    ) -> VoiceEffect:
        if isinstance(target, VoiceInlineTarget):
            return DiscardInlineDictation(target.interaction_id, message)
        return (
            RestoreVoiceFollowUp(capture_id, target, message)
            if isinstance(target, VoiceFollowUpTarget)
            else RestoreVoiceReview(target, message)
        )

    def _finalize_effect(
        self,
        capture_id: VoiceCaptureId,
        target: VoiceCaptureTarget,
        text: str,
        warning: str,
        *,
        inline_delivery: bool | None = None,
    ) -> VoiceEffect:
        if isinstance(target, VoiceInlineTarget):
            if target.paste_target is None:
                recovery_message = "No paste target is available. Copy the text and paste it manually."
                if warning:
                    recovery_message = f"{warning} {recovery_message}"
                self._pending_inline = _PendingInline(text, target, recovery_message=recovery_message)
                return PresentInlineRecovery(target.interaction_id, text, self._pending_inline.recovery_message)
            self._pending_inline = _PendingInline(text, target)
            if target.mode == "minimal" and inline_delivery is not None:
                return self.confirm_inline_settlement(target.interaction_id, inline_delivery).effects[0]
            return PresentInlineChoice(target.interaction_id, text, message=warning)
        return (
            FinalizeVoiceFollowUp(capture_id, target, text, warning)
            if isinstance(target, VoiceFollowUpTarget)
            else FinalizeVoiceDraft(capture_id, target, text, warning)
        )

    def _matching_capture(self, capture_id: VoiceCaptureId) -> _Capture | None:
        capture = self._capture
        return capture if capture is not None and capture.capture_id == capture_id else None

    @staticmethod
    def _listening_message(capture: _Capture) -> str:
        remaining = capture.remaining_seconds
        if remaining is not None and remaining <= 30:
            return (
                f"Listening… · {remaining} seconds remaining; "
                "this section will be saved automatically."
            )
        return "Listening…"

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


def _inline_paste_message(outcome: PasteOutcome) -> str:
    if outcome.state == "dispatched_unconfirmed":
        return "Paste shortcut sent. Check the original text field before continuing."
    if outcome.state == "cleanup_failed":
        return "Paste or clipboard restoration could not be confirmed. Check the original field and clipboard."
    if outcome.state == "cancelled":
        return "Dictation cancelled. No paste was dispatched."
    return "Nothing was pasted. Your recognized text remains available to copy."
