from __future__ import annotations

from ClipAI.core.models import PasteTarget
from ClipAI.core.voice import (
    VoiceCaptureId,
    VoiceCapabilityPhase,
    VoiceDraftTarget,
    VoiceEngineEnded,
    VoiceEngineFinalSegment,
    VoiceEngineInterim,
    VoiceEngineListening,
    VoiceEngineSetupReady,
    VoiceSetupId,
)
from ClipAI.services.voice_input import (
    CancelVoiceCapture,
    FinalizeVoiceDraft,
    PrepareVoiceSetup,
    StartVoiceCapture,
    StopVoiceCapture,
    VoiceInputController,
)


def target() -> VoiceDraftTarget:
    return VoiceDraftTarget(
        "workflow-1",
        3,
        PasteTarget("hwnd:1", 1, "Editor", "private title", 1),
        2,
        2,
    )


def ready_controller() -> VoiceInputController:
    controller = VoiceInputController()
    setup = VoiceSetupId("setup-1")
    assert controller.request_setup(setup).effects == (PrepareVoiceSetup(setup, "zh-TW"),)
    controller.observe_engine(VoiceEngineSetupReady(setup))
    return controller


def test_setup_is_identity_scoped_and_ready_only_after_its_terminal_event() -> None:
    controller = VoiceInputController()
    setup = VoiceSetupId("setup-1")

    transition = controller.request_setup(setup)

    assert transition.effects == (PrepareVoiceSetup(setup, "zh-TW"),)
    assert controller.observe_engine(VoiceEngineSetupReady(VoiceSetupId("old"))).ignored is True
    assert controller.projection.capability is VoiceCapabilityPhase.REQUESTING_PERMISSION
    assert controller.observe_engine(VoiceEngineSetupReady(setup)).projection.capability is VoiceCapabilityPhase.READY


def test_capture_admission_is_single_flight_and_listening_waits_for_engine_ack() -> None:
    controller = ready_controller()
    capture = VoiceCaptureId("capture-1")

    starting = controller.request_capture(capture, target())

    assert starting.effects == (StartVoiceCapture(capture, "zh-TW"),)
    assert controller.request_capture(VoiceCaptureId("capture-2"), target()).ignored is True
    assert controller.observe_engine(VoiceEngineListening(capture)).projection.capture_phase.value == "listening"


def test_release_is_a_monotonic_stop_gate_and_late_interim_is_ignored() -> None:
    controller = ready_controller()
    capture = VoiceCaptureId("capture-1")
    controller.request_capture(capture, target())

    stopped = controller.request_stop(capture)

    assert stopped.effects == (StopVoiceCapture(capture),)
    assert controller.request_stop(capture).ignored is True
    assert controller.observe_engine(VoiceEngineInterim(capture, "late")).ignored is True


def test_terminal_applies_ordered_final_segments_once() -> None:
    controller = ready_controller()
    capture = VoiceCaptureId("capture-1")
    frozen_target = target()
    controller.request_capture(capture, frozen_target)
    controller.observe_engine(VoiceEngineFinalSegment(capture, 1, "world"))
    controller.observe_engine(VoiceEngineFinalSegment(capture, 0, "hello"))

    terminal = controller.observe_engine(VoiceEngineEnded(capture))

    assert terminal.effects == (FinalizeVoiceDraft(capture, frozen_target, "hello world"),)
    assert controller.observe_engine(VoiceEngineEnded(capture)).ignored is True


def test_cancel_discards_provisional_and_finalized_capture_content() -> None:
    controller = ready_controller()
    capture = VoiceCaptureId("capture-1")
    controller.request_capture(capture, target())
    controller.observe_engine(VoiceEngineFinalSegment(capture, 0, "discard me"))

    assert controller.request_cancel(capture).effects == (CancelVoiceCapture(capture),)
    assert controller.observe_engine(VoiceEngineEnded(capture)).effects == ()
    assert controller.projection.capture_id is None


def test_conflicting_duplicate_segment_fails_the_capture() -> None:
    controller = ready_controller()
    capture = VoiceCaptureId("capture-1")
    controller.request_capture(capture, target())
    controller.observe_engine(VoiceEngineFinalSegment(capture, 0, "first"))

    transition = controller.observe_engine(VoiceEngineFinalSegment(capture, 0, "different"))

    assert transition.effects == ()
    assert controller.projection.capture_id is None
    assert "invalid recognition response" in controller.projection.message
