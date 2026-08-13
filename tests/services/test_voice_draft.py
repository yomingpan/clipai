from __future__ import annotations

import pytest

from ClipAI.core.models import PasteTarget
from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.core.voice import VoiceCapturePhase, VoiceDraftInsertion, VoiceLanguage, VoiceOrigin, VoiceProjection
from ClipAI.services import voice_draft


def draft_snapshot(
    text: str = "hello",
    *,
    status: SessionStatus = SessionStatus.VOICE_REVIEW,
    revision: int = 0,
    displayed_step_index: int = -1,
) -> SessionSnapshot:
    return SessionSnapshot(
        "voice-workflow",
        revision,
        status,
        "voice_input",
        "Voice Input",
        "",
        content=text,
        available_actions=("copy", "paste", "follow_up"),
        result_completeness="complete",
        displayed_step_index=displayed_step_index,
        voice_origin=VoiceOrigin(
            PasteTarget("hwnd:1", 1, "Editor", "private", 1),
            text,
        ),
    )


def projection(
    phase: VoiceCapturePhase,
    *,
    workflow_id: str = "voice-workflow",
) -> VoiceProjection:
    return VoiceProjection(
        capability="ready",
        language=VoiceLanguage("zh-TW"),
        capture_id="capture-1",
        capture_phase=phase,
        message="Listening...",
        workflow_id=workflow_id,
    )


def test_freeze_insertion_captures_revision_target_and_selection() -> None:
    snapshot = draft_snapshot("hello world")

    target = voice_draft.freeze_insertion(snapshot, 6, 11)

    assert target is not None
    assert target.workflow_id == "voice-workflow"
    assert target.expected_revision == 0
    assert target.paste_target == snapshot.voice_origin.paste_target
    assert (target.selection_start, target.selection_end) == (6, 11)


@pytest.mark.parametrize("selection", [(-1, 0), (3, 2), (0, 6)])
def test_freeze_insertion_rejects_invalid_selection(selection: tuple[int, int]) -> None:
    assert voice_draft.freeze_insertion(draft_snapshot(), *selection) is None


def test_freeze_insertion_rejects_non_review_or_active_invocation() -> None:
    assert voice_draft.freeze_insertion(
        draft_snapshot(status=SessionStatus.VOICE_LISTENING),
        0,
        0,
    ) is None
    assert voice_draft.freeze_insertion(
        draft_snapshot().evolve(active_invocation_id="invoke-1"),
        0,
        0,
    ) is None


def test_finalize_capture_splices_text_and_advances_draft_revision() -> None:
    snapshot = draft_snapshot("hello world")
    target = voice_draft.freeze_insertion(snapshot, 6, 11)
    assert target is not None

    finalized = voice_draft.finalize_capture(snapshot, target, "ClipAI")

    assert finalized is not None
    assert finalized.content == "hello ClipAI"
    assert finalized.voice_origin is not None
    assert finalized.voice_origin.text == "hello ClipAI"
    assert finalized.voice_origin.revision == 1
    assert finalized.voice_origin.latest_insertion == VoiceDraftInsertion(1, 6, 12)
    assert finalized.status is SessionStatus.VOICE_REVIEW
    assert finalized.voice_capture_id is None


def test_targetless_draft_can_freeze_and_finalize_without_a_paste_destination() -> None:
    snapshot = draft_snapshot("").evolve(voice_origin=VoiceOrigin(None))

    target = voice_draft.freeze_insertion(snapshot, 0, 0)
    assert target is not None
    assert target.paste_target is None

    finalized = voice_draft.finalize_capture(snapshot, target, "hello")

    assert finalized is not None
    assert finalized.content == "hello"
    assert finalized.voice_origin == VoiceOrigin(
        None,
        "hello",
        1,
        VoiceDraftInsertion(2, 0, 5),
    )


def test_stale_capture_cannot_overwrite_a_newer_edit() -> None:
    snapshot = draft_snapshot()
    target = voice_draft.freeze_insertion(snapshot, 5, 5)
    assert target is not None
    edited = voice_draft.edit_draft(snapshot, 0, "edited")
    assert edited is not None

    assert voice_draft.finalize_capture(edited, target, " late") is None


def test_finalize_capture_rejects_blank_text_or_mismatched_target() -> None:
    snapshot = draft_snapshot()
    target = voice_draft.freeze_insertion(snapshot, 5, 5)
    assert target is not None

    assert voice_draft.finalize_capture(snapshot, target, "  ") is None
    assert voice_draft.finalize_capture(
        snapshot,
        type(target)(
            target.workflow_id,
            target.expected_revision,
            PasteTarget("hwnd:2", 2, "Other", "private", 2),
            target.selection_start,
            target.selection_end,
        ),
        "text",
    ) is None


def test_edit_draft_requires_the_current_review_revision() -> None:
    snapshot = draft_snapshot("hello world")
    target = voice_draft.freeze_insertion(snapshot, 6, 11)
    assert target is not None
    snapshot = voice_draft.finalize_capture(snapshot, target, "ClipAI")
    assert snapshot is not None

    edited = voice_draft.edit_draft(snapshot, 1, "edited")

    assert edited is not None
    assert edited.content == "edited"
    assert edited.voice_origin is not None
    assert edited.voice_origin.revision == 2
    assert edited.voice_origin.latest_insertion is None
    assert voice_draft.edit_draft(edited, 0, "stale") is None
    assert voice_draft.edit_draft(
        draft_snapshot(status=SessionStatus.VOICE_LISTENING),
        0,
        "wrong phase",
    ) is None


@pytest.mark.parametrize(
    ("phase", "status"),
    [
        (VoiceCapturePhase.STARTING, SessionStatus.VOICE_PREPARING),
        (VoiceCapturePhase.LISTENING, SessionStatus.VOICE_LISTENING),
        (VoiceCapturePhase.STOP_REQUESTED, SessionStatus.VOICE_FINALIZING),
        (VoiceCapturePhase.FINALIZING, SessionStatus.VOICE_FINALIZING),
        (VoiceCapturePhase.CANCEL_REQUESTED, SessionStatus.VOICE_FINALIZING),
    ],
)
def test_project_capture_maps_capture_phase_without_changing_draft(
    phase: VoiceCapturePhase,
    status: SessionStatus,
) -> None:
    snapshot = draft_snapshot()

    projected = voice_draft.project_capture(snapshot, projection(phase))

    assert projected is not None
    assert projected.status is status
    assert projected.voice_capture_id == "capture-1"
    assert projected.available_actions == ()
    assert projected.voice_origin == snapshot.voice_origin


def test_project_capture_rejects_wrong_workflow_or_terminal_phase() -> None:
    snapshot = draft_snapshot()

    assert voice_draft.project_capture(
        snapshot,
        projection(VoiceCapturePhase.LISTENING, workflow_id="other"),
    ) is None
    assert voice_draft.project_capture(
        snapshot,
        projection(VoiceCapturePhase.TERMINAL),
    ) is None


def test_restore_review_requires_the_frozen_revision() -> None:
    snapshot = draft_snapshot()
    target = voice_draft.freeze_insertion(snapshot, 5, 5)
    assert target is not None
    listening = voice_draft.project_capture(
        snapshot,
        projection(VoiceCapturePhase.LISTENING),
    )
    assert listening is not None

    restored = voice_draft.restore_review(listening, target, "Try again.")

    assert restored is not None
    assert restored.status is SessionStatus.VOICE_REVIEW
    assert restored.content == "hello"
    assert restored.status_text == "Try again."
    assert restored.voice_capture_id is None
    edited = voice_draft.edit_draft(snapshot, 0, "newer")
    assert edited is not None
    assert voice_draft.restore_review(edited, target, "stale") is None


def test_return_to_review_restores_origin_only_from_first_action_result() -> None:
    snapshot = draft_snapshot(displayed_step_index=0).evolve(
        status=SessionStatus.COMPLETED,
        action_id="rewrite",
        title="Rewrite",
        content="rewritten",
    )

    assert voice_draft.can_return_to_review(snapshot) is True
    restored = voice_draft.return_to_review(snapshot)

    assert restored is not None
    assert restored.status is SessionStatus.VOICE_REVIEW
    assert restored.action_id == "voice_input"
    assert restored.content == "hello"
    assert restored.displayed_step_index == -1
    assert restored.can_navigate_back is False
    assert voice_draft.return_to_review(
        draft_snapshot(displayed_step_index=1),
    ) is None
