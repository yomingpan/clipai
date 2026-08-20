from __future__ import annotations

from dataclasses import replace

from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.core.voice import VoiceCapturePhase, VoiceDraftInsertion, VoiceDraftTarget, VoiceProjection


def freeze_insertion(
    snapshot: SessionSnapshot,
    selection_start: int,
    selection_end: int,
) -> VoiceDraftTarget | None:
    """Freeze one insertion range against the current canonical Voice Draft."""
    origin = snapshot.voice_origin
    if (
        origin is None
        or snapshot.status is not SessionStatus.VOICE_REVIEW
        or snapshot.active_invocation_id is not None
        or selection_start < 0
        or selection_end < selection_start
        or selection_end > len(origin.text)
    ):
        return None
    return VoiceDraftTarget(
        snapshot.session_id,
        origin.revision,
        origin.paste_target,
        selection_start,
        selection_end,
    )


def project_capture(
    snapshot: SessionSnapshot,
    projection: VoiceProjection,
) -> SessionSnapshot | None:
    """Project capture lifecycle without changing canonical Voice Draft text."""
    if projection.workflow_id != snapshot.session_id or projection.capture_phase is None:
        return None
    status = {
        VoiceCapturePhase.STARTING: SessionStatus.VOICE_PREPARING,
        VoiceCapturePhase.LISTENING: SessionStatus.VOICE_LISTENING,
        VoiceCapturePhase.STOP_REQUESTED: SessionStatus.VOICE_FINALIZING,
        VoiceCapturePhase.FINALIZING: SessionStatus.VOICE_FINALIZING,
        VoiceCapturePhase.CANCEL_REQUESTED: SessionStatus.VOICE_FINALIZING,
    }.get(projection.capture_phase)
    if status is None or snapshot.voice_origin is None:
        return None
    return snapshot.evolve(
        status=status,
        status_text=projection.message,
        available_actions=(),
        result_completeness="none",
        voice_capture_id=projection.capture_id,
        voice_capture_phase=projection.capture_phase,
        voice_audio_level=projection.audio_level,
        voice_silence_detected=projection.silence_detected,
        voice_status_text=projection.message,
    )


def restore_review(
    snapshot: SessionSnapshot,
    target: VoiceDraftTarget,
    message: str,
) -> SessionSnapshot | None:
    """Restore Review for the unchanged Voice Draft captured by target."""
    origin = snapshot.voice_origin
    if (
        origin is None
        or target.workflow_id != snapshot.session_id
        or target.expected_revision != origin.revision
    ):
        return None
    return snapshot.evolve(
        status=SessionStatus.VOICE_REVIEW,
        content=origin.text,
        status_text=message,
        result_completeness="complete",
        available_actions=("copy", "paste", "follow_up"),
        voice_capture_id=None,
        voice_capture_phase=None,
        voice_audio_level=0.0,
        voice_silence_detected=False,
        voice_status_text=message,
    )


def finalize_capture(
    snapshot: SessionSnapshot,
    target: VoiceDraftTarget,
    text: str,
) -> SessionSnapshot | None:
    """Apply settled capture text only to its frozen Voice Draft target."""
    if not text.strip():
        return None
    origin = snapshot.voice_origin
    if (
        origin is None
        or target.workflow_id != snapshot.session_id
        or target.expected_revision != origin.revision
        or target.paste_target != origin.paste_target
        or target.selection_end > len(origin.text)
    ):
        return None
    content = f"{origin.text[:target.selection_start]}{text}{origin.text[target.selection_end:]}"
    revision = origin.revision + 1
    insertion = VoiceDraftInsertion(
        snapshot.revision + 1,
        target.selection_start,
        target.selection_start + len(text),
    )
    return snapshot.evolve(
        status=SessionStatus.VOICE_REVIEW,
        title="Voice Input",
        action_id="voice_input",
        content=content,
        original_input="",
        source_preview="Voice Input draft",
        error="",
        active_invocation_id=None,
        displayed_step_index=-1,
        can_navigate_back=False,
        presentation=None,
        action_feedback_contract=None,
        input_source="voice_transcript",
        feedback_state="idle",
        feedback_step_id="",
        feedback_operation_id="",
        feedback_message="",
        show_guidance_hint=False,
        result_completeness="complete",
        available_actions=("copy", "paste", "follow_up"),
        voice_origin=replace(
            origin,
            text=content,
            revision=revision,
            latest_insertion=insertion,
        ),
        voice_capture_id=None,
        voice_capture_phase=None,
        voice_audio_level=0.0,
        voice_silence_detected=False,
        voice_status_text="Review your dictation.",
    )


def edit_draft(
    snapshot: SessionSnapshot,
    expected_revision: int,
    text: str,
) -> SessionSnapshot | None:
    """Replace canonical Voice Draft text when its revision still matches."""
    origin = snapshot.voice_origin
    if (
        origin is None
        or snapshot.status is not SessionStatus.VOICE_REVIEW
        or origin.revision != expected_revision
    ):
        return None
    return snapshot.evolve(
        content=text,
        voice_origin=replace(
            origin,
            text=text,
            revision=origin.revision + 1,
            latest_insertion=None,
        ),
    )


def can_return_to_review(snapshot: SessionSnapshot) -> bool:
    return snapshot.voice_origin is not None


def return_to_review(snapshot: SessionSnapshot) -> SessionSnapshot | None:
    """Return from the first Action result to its canonical Voice Draft."""
    origin = snapshot.voice_origin
    if origin is None or snapshot.displayed_step_index != 0:
        return None
    return snapshot.evolve(
        status=SessionStatus.VOICE_REVIEW,
        title="Voice Input",
        action_id="voice_input",
        content=origin.text,
        original_input="",
        source_preview="Voice Input draft",
        error="",
        displayed_step_index=-1,
        can_navigate_back=False,
        presentation=None,
        action_feedback_contract=None,
        input_source="voice_transcript",
        feedback_state="idle",
        feedback_step_id="",
        feedback_operation_id="",
        feedback_message="",
        show_guidance_hint=False,
        result_completeness="complete",
        available_actions=("copy", "paste", "follow_up"),
    )
