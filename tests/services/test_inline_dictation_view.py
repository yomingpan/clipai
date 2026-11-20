import pytest

from ClipAI.core.models import PasteTarget, PasteOutcome
from ClipAI.core.voice import VoiceCaptureId, VoiceInlineTarget, VoiceEngineListening, VoiceEngineFinalSegment, VoiceEngineEnded, VoiceDraftTarget
from ClipAI.services.voice_input import VoiceInputController, PasteInlineDictation
from ClipAI.core.voice import VoiceEngineFailed, VoiceTransportFailure


TARGET = PasteTarget("hwnd:1", 42, "controlled", "", 1)


@pytest.mark.parametrize("failure", list(VoiceTransportFailure))
@pytest.mark.parametrize("partial", [False, True])
def test_capture_failure_projects_typed_reason_without_losing_partial_content(failure, partial):
    controller = VoiceInputController(enabled=True)
    capture = VoiceCaptureId("capture-notice")
    controller.request_capture(capture, VoiceInlineTarget("notice", TARGET, "minimal"))
    if partial:
        controller.observe_engine(VoiceEngineFinalSegment(capture, 0, "preserved"))
    result = controller.observe_engine(VoiceEngineFailed(capture, failure, "arbitrary diagnostic detail"))
    assert result.inline_view.capture_notice == failure
    assert result.inline_view.phase == ("awaiting" if partial else "closed")
    assert result.inline_view.text == ("preserved" if partial else "")
    assert not any(isinstance(effect, PasteInlineDictation) for effect in result.effects)
    if partial:
        copied = controller.request_inline_copy("notice")
        assert copied.effects[-1].text == "preserved"
        assert copied.inline_view.capture_notice == failure


def test_no_speech_is_distinct_from_a_transport_failure():
    controller = VoiceInputController(enabled=True)
    capture = VoiceCaptureId("empty")
    controller.request_capture(capture, VoiceInlineTarget("notice", TARGET, "minimal"))
    controller.request_stop(capture)
    result = controller.observe_engine(VoiceEngineEnded(capture))
    assert result.inline_view.phase == "closed"
    assert result.inline_view.capture_notice == "no_speech"


@pytest.mark.parametrize("mode", ["minimal", "choice"])
def test_automatic_stop_projects_awaiting_without_delivery_intent_or_paste(mode):
    controller = VoiceInputController(enabled=True)
    capture = VoiceCaptureId("c-1")
    started = controller.request_capture(capture, VoiceInlineTarget("i-1", TARGET, mode))
    assert started.inline_view.phase == "starting"
    assert controller.observe_engine(VoiceEngineListening(capture)).inline_view.phase == "listening"
    controller.observe_engine(VoiceEngineFinalSegment(capture, 0, "original"))
    stopped = controller.request_stop(capture)
    assert stopped.inline_view.phase == "finalizing"
    assert stopped.inline_view.chosen is None
    settled = controller.observe_engine(VoiceEngineEnded(capture))
    assert settled.inline_view.phase == "awaiting"
    assert settled.inline_view.text == "original"
    assert settled.inline_view.chosen is None
    assert not any(isinstance(effect, PasteInlineDictation) for effect in settled.effects)


def test_workflow_voice_never_produces_an_inline_view():
    controller = VoiceInputController(enabled=True)
    transition = controller.request_capture(VoiceCaptureId("c-1"), VoiceDraftTarget("w-1", 0, TARGET, 0, 0))
    assert transition.inline_view is None


@pytest.mark.parametrize("mode", ["minimal", "choice"])
def test_explicit_refine_stop_preserves_choice_through_paste_settlement(mode):
    controller = VoiceInputController(enabled=True)
    capture = VoiceCaptureId("c-1")
    controller.request_capture(capture, VoiceInlineTarget("i-1", TARGET, mode))
    controller.observe_engine(VoiceEngineFinalSegment(capture, 0, "original"))
    stopped = controller.confirm_inline_settlement("i-1", refine=True)
    assert stopped.inline_view.phase == "finalizing"
    assert stopped.inline_view.chosen == "refine"
    refining = controller.observe_engine(VoiceEngineEnded(capture))
    assert refining.inline_view.phase == "finalizing"
    operation = next(effect for effect in refining.effects if isinstance(effect, PasteInlineDictation))
    assert controller.accept_inline_refinement_admission("i-1", operation.operation_id).inline_view.phase == "refining"
    pasting = controller.complete_inline_refinement("i-1", operation.operation_id, "refined")
    assert pasting.inline_view.phase == "pasting"
    paste = next(effect for effect in pasting.effects if isinstance(effect, PasteInlineDictation))
    settled = controller.complete_inline_paste("i-1", paste.operation_id, PasteOutcome("dispatched_unconfirmed", "dispatched_unconfirmed", "restored"))
    assert settled.inline_view.phase == "settled"
    assert settled.inline_view.chosen == "refine"
    assert settled.inline_view.text == "refined"


def awaiting_controller():
    controller = VoiceInputController(enabled=True)
    capture = VoiceCaptureId("c-1")
    controller.request_capture(capture, VoiceInlineTarget("i-1", TARGET, "minimal"))
    controller.observe_engine(VoiceEngineFinalSegment(capture, 0, "original"))
    controller.request_stop(capture)
    controller.observe_engine(VoiceEngineEnded(capture))
    return controller


def test_failed_refinement_preserves_raw_copy_and_disables_refinement():
    controller = awaiting_controller()
    operation = controller.confirm_inline_settlement("i-1", True).effects[0]
    failed = controller.complete_inline_refinement("i-1", operation.operation_id, error=True)
    assert failed.inline_view.phase == "awaiting"
    assert failed.inline_view.text == "original"
    assert not failed.inline_view.allow_refine
    assert controller.confirm_inline_settlement("i-1", True).ignored
    copying = controller.request_inline_copy("i-1")
    assert copying.inline_view.copy_state == "pending"
    copy = copying.effects[-1]
    assert copy.text == "original"
    assert controller.complete_inline_copy("i-1", copy.operation_id).inline_view.copy_state == "succeeded"


def test_discard_projects_closed_once_and_late_discard_does_not_close_new_capture():
    controller = awaiting_controller()
    assert controller.cancel_inline("i-1").inline_view.phase == "closed"
    assert controller.cancel_inline("i-1").inline_view is None
    controller.request_capture(VoiceCaptureId("c-2"), VoiceInlineTarget("i-2", TARGET, "choice"))
    assert controller.cancel_inline("i-1").ignored
    assert controller.inline_view.interaction_id == "i-2"


def test_preview_is_identity_scoped_and_never_a_delivery_intent():
    controller = awaiting_controller()
    assert controller.preview_inline_refinement("old").ignored
    preview = controller.preview_inline_refinement("i-1")
    assert preview.inline_view.preview_refine
    assert preview.inline_view.chosen is None
    assert preview.effects == ()
    cleared = controller.preview_inline_refinement("i-1", active=False)
    assert not cleared.inline_view.preview_refine
    assert cleared.effects == ()


def test_first_stop_locks_delivery_and_preview_until_awaiting():
    controller = VoiceInputController(enabled=True)
    capture = VoiceCaptureId("c-1")
    controller.request_capture(capture, VoiceInlineTarget("i-1", TARGET, "choice"))
    assert controller.preview_inline_refinement("i-1").inline_view.preview_refine
    assert controller.confirm_inline_settlement("i-1").inline_view.chosen == "raw"
    assert controller.confirm_inline_settlement("i-1", True).ignored
    assert controller.preview_inline_refinement("i-1").ignored
    assert controller.inline_view.chosen == "raw"
    assert not controller.inline_view.preview_refine


@pytest.mark.parametrize("outcome, phase", [
    (PasteOutcome("cancelled", "not_dispatched", "not_required"), "settled"),
    (PasteOutcome("failed", "not_dispatched", "not_required"), "recovery"),
    (PasteOutcome("cleanup_failed", "dispatched_unconfirmed", "failed"), "recovery"),
])
def test_paste_truth_projects_terminal_or_recovery_without_claiming_success(outcome, phase):
    controller = awaiting_controller()
    paste = controller.confirm_inline_settlement("i-1").effects[0]
    assert controller.complete_inline_paste("i-1", paste.operation_id, outcome).inline_view.phase == phase
    assert controller.inline_view.paste_outcome == outcome
    assert controller.inline_view.text == "original"
    assert controller.complete_inline_paste("i-1", "stale", outcome).ignored


def test_refinement_cancel_timeout_preserves_copy_and_identity_scoped_retry():
    controller = awaiting_controller()
    refine = controller.confirm_inline_settlement("i-1", True).effects[0]
    assert controller.cancel_inline("i-1").inline_view.phase == "cancelling"
    timed_out = controller.note_inline_refinement_cancel_timeout("i-1", refine.operation_id)
    assert timed_out.inline_view.phase == "cancel_unconfirmed"
    assert timed_out.inline_view.text == "original"
    assert controller.request_inline_copy("i-1").inline_view.copy_state == "pending"
    assert controller.cancel_inline("i-1").inline_view.phase == "cancelling"
