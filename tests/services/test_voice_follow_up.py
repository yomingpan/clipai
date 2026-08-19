from __future__ import annotations

from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.core.voice import (
    VoiceCaptureDestination,
    VoiceCaptureId,
    VoiceCapturePhase,
    VoiceCapabilityPhase,
    VoiceFollowUpTarget,
    VoiceProjection,
)
from ClipAI.services import voice_follow_up


def completed_snapshot() -> SessionSnapshot:
    return SessionSnapshot(
        "workflow-1",
        4,
        SessionStatus.COMPLETED,
        "summarize",
        "Summarize",
        "model",
        content="answer",
        available_actions=("copy", "follow_up"),
    )


def test_follow_up_capture_projects_lifecycle_without_replacing_result_content() -> None:
    snapshot = completed_snapshot()
    projection = VoiceProjection(
        VoiceCapabilityPhase.READY,
        "zh-TW",
        VoiceCaptureId("capture-1"),
        VoiceCapturePhase.LISTENING,
        message="Listening…",
        workflow_id="workflow-1",
        audio_level=0.4,
        capture_destination=VoiceCaptureDestination.FOLLOW_UP,
    )

    updated = voice_follow_up.project_capture(snapshot, projection)

    assert updated is not None
    assert updated.status is SessionStatus.COMPLETED
    assert updated.content == "answer"
    assert updated.voice_audio_level == 0.4


def test_follow_up_finalization_is_an_identity_scoped_one_time_insertion_projection() -> None:
    target = VoiceFollowUpTarget("workflow-1")
    snapshot = completed_snapshot().evolve(
        voice_capture_id=VoiceCaptureId("capture-1"),
        voice_capture_phase=VoiceCapturePhase.FINALIZING,
    )

    updated = voice_follow_up.finalize(
        snapshot,
        VoiceCaptureId("capture-1"),
        target,
        "What changed?",
    )

    assert updated is not None
    assert updated.voice_follow_up_insertion is not None
    assert updated.voice_follow_up_insertion.capture_id == "capture-1"
    assert updated.voice_follow_up_insertion.text == "What changed?"
    assert updated.voice_capture_id is None


def test_follow_up_projection_rejects_provider_activity_and_wrong_workflow() -> None:
    snapshot = completed_snapshot().evolve(
        active_invocation_id="provider-1",
        voice_capture_id=VoiceCaptureId("capture-1"),
        voice_capture_phase=VoiceCapturePhase.FINALIZING,
    )
    projection = VoiceProjection(
        VoiceCapabilityPhase.READY,
        "zh-TW",
        VoiceCaptureId("capture-1"),
        VoiceCapturePhase.STARTING,
        workflow_id="workflow-1",
        capture_destination=VoiceCaptureDestination.FOLLOW_UP,
    )

    assert voice_follow_up.project_capture(snapshot, projection) is None
    assert voice_follow_up.finalize(snapshot, "capture-1", VoiceFollowUpTarget("other"), "late") is None


def test_stale_follow_up_settlement_cannot_touch_a_newer_capture() -> None:
    snapshot = completed_snapshot().evolve(
        voice_capture_id=VoiceCaptureId("capture-new"),
        voice_capture_phase=VoiceCapturePhase.LISTENING,
    )
    target = VoiceFollowUpTarget("workflow-1")

    assert voice_follow_up.restore(snapshot, VoiceCaptureId("capture-old"), target, "late") is None
    assert voice_follow_up.finalize(
        snapshot,
        VoiceCaptureId("capture-old"),
        target,
        "late transcript",
    ) is None
