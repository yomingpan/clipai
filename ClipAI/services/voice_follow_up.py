from __future__ import annotations

from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.core.voice import (
    VoiceCaptureDestination,
    VoiceCaptureId,
    VoiceFollowUpInsertion,
    VoiceFollowUpTarget,
    VoiceProjection,
)


_FOLLOW_UP_READY_STATUSES = {
    SessionStatus.COMPLETED,
    SessionStatus.FAILED,
    SessionStatus.STOPPED,
    SessionStatus.VOICE_REVIEW,
}


def project_capture(
    snapshot: SessionSnapshot,
    projection: VoiceProjection,
) -> SessionSnapshot | None:
    if (
        projection.capture_destination is not VoiceCaptureDestination.FOLLOW_UP
        or projection.workflow_id != snapshot.session_id
        or projection.capture_phase is None
        or snapshot.status not in _FOLLOW_UP_READY_STATUSES
        or snapshot.active_invocation_id is not None
    ):
        return None
    return snapshot.evolve(
        voice_capture_id=projection.capture_id,
        voice_capture_phase=projection.capture_phase,
        voice_audio_level=projection.audio_level,
        voice_silence_detected=projection.silence_detected,
        voice_status_text=projection.message,
    )


def restore(
    snapshot: SessionSnapshot,
    capture_id: VoiceCaptureId,
    target: VoiceFollowUpTarget,
    message: str,
) -> SessionSnapshot | None:
    if (
        target.workflow_id != snapshot.session_id
        or snapshot.voice_capture_id != capture_id
    ):
        return None
    return snapshot.evolve(
        voice_capture_id=None,
        voice_capture_phase=None,
        voice_audio_level=0.0,
        voice_silence_detected=False,
        voice_status_text=message,
    )


def finalize(
    snapshot: SessionSnapshot,
    capture_id: VoiceCaptureId,
    target: VoiceFollowUpTarget,
    text: str,
) -> SessionSnapshot | None:
    if (
        target.workflow_id != snapshot.session_id
        or snapshot.voice_capture_id != capture_id
        or snapshot.status not in _FOLLOW_UP_READY_STATUSES
        or snapshot.active_invocation_id is not None
        or not text.strip()
    ):
        return None
    return snapshot.evolve(
        voice_capture_id=None,
        voice_capture_phase=None,
        voice_audio_level=0.0,
        voice_silence_detected=False,
        voice_status_text="Review your dictation.",
        voice_follow_up_insertion=VoiceFollowUpInsertion(capture_id, text),
    )
