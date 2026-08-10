from __future__ import annotations

from ClipAI.core.models import PasteTarget
from ClipAI.core.models import ShortcutPressId
from ClipAI.core.voice import (
    VoiceCaptureId,
    VoiceCapabilityPhase,
    VoiceDisableId,
    VoiceLanguageChangeId,
    VoiceDraftTarget,
    VoiceEngineEnded,
    VoiceEngineFinalSegment,
    VoiceEngineFailed,
    VoiceEngineInterim,
    VoiceEngineListening,
    VoiceEngineSetupReady,
    VoiceLanguage,
    VoiceSetupId,
    VoiceTransportFailure,
)
from ClipAI.services.voice_input import (
    CancelVoiceCapture,
    FinalizeVoiceDraft,
    PersistVoiceEnabled,
    PersistVoiceDisabled,
    PersistVoiceLanguage,
    PrepareVoiceSetup,
    RestoreVoiceReview,
    StartVoiceCapture,
    ShutdownVoiceEngine,
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
    controller.complete_enable_save(setup)
    return controller


def test_setup_is_identity_scoped_and_ready_only_after_its_terminal_event() -> None:
    controller = VoiceInputController()
    setup = VoiceSetupId("setup-1")

    transition = controller.request_setup(setup)

    assert transition.effects == (PrepareVoiceSetup(setup, "zh-TW"),)
    assert controller.observe_engine(VoiceEngineSetupReady(VoiceSetupId("old"))).ignored is True
    assert controller.projection.capability is VoiceCapabilityPhase.REQUESTING_PERMISSION
    saving = controller.observe_engine(VoiceEngineSetupReady(setup))
    assert saving.projection.capability is VoiceCapabilityPhase.REQUESTING_PERMISSION
    assert saving.effects == (PersistVoiceEnabled(setup),)
    assert controller.complete_enable_save(setup).projection.capability is VoiceCapabilityPhase.READY


def test_setup_preference_save_failure_leaves_voice_input_retriable() -> None:
    controller = VoiceInputController()
    setup = VoiceSetupId("setup-1")
    controller.request_setup(setup)
    controller.observe_engine(VoiceEngineSetupReady(setup))

    transition = controller.complete_enable_save(setup, "disk unavailable")

    assert transition.projection.capability is VoiceCapabilityPhase.SETUP_REQUIRED


def test_capture_admission_is_single_flight_and_listening_waits_for_engine_ack() -> None:
    controller = ready_controller()
    capture = VoiceCaptureId("capture-1")

    starting = controller.request_capture(capture, target())

    assert starting.effects == (StartVoiceCapture(capture, "zh-TW"),)
    assert controller.request_capture(VoiceCaptureId("capture-2"), target()).ignored is True
    assert controller.observe_engine(VoiceEngineListening(capture)).projection.capture_phase.value == "listening"


def test_capture_permission_failure_requires_explicit_setup_repair() -> None:
    controller = ready_controller()
    capture = VoiceCaptureId("capture-1")
    controller.request_capture(capture, target())

    transition = controller.observe_engine(VoiceEngineFailed(
        capture,
        VoiceTransportFailure.PERMISSION_DENIED,
    ))

    assert transition.projection.capability is VoiceCapabilityPhase.PERMISSION_BLOCKED
    assert transition.projection.capture_id is None
    assert isinstance(transition.effects[0], RestoreVoiceReview)


def test_missing_microphone_returns_a_retriable_review_with_a_remedy() -> None:
    controller = ready_controller()
    capture = VoiceCaptureId("capture-1")
    controller.request_capture(capture, target())

    transition = controller.observe_engine(VoiceEngineFailed(
        capture,
        VoiceTransportFailure.UNAVAILABLE,
        "No microphone was detected. Connect one and try again.",
    ))

    assert transition.projection.capability is VoiceCapabilityPhase.READY
    assert transition.effects == (
        RestoreVoiceReview(target(), "No microphone was detected. Connect one and try again."),
    )


def test_release_is_a_monotonic_stop_gate_and_late_interim_is_ignored() -> None:
    controller = ready_controller()
    capture = VoiceCaptureId("capture-1")
    controller.request_capture(capture, target())

    stopped = controller.request_stop(capture)

    assert stopped.effects == (StopVoiceCapture(capture),)
    assert controller.request_stop(capture).ignored is True
    assert controller.observe_engine(VoiceEngineInterim(capture, "late")).ignored is True


def test_controller_owns_press_to_capture_mapping_and_rejects_stale_release() -> None:
    controller = ready_controller()
    press_id = ShortcutPressId(7)
    started = controller.request_capture_for_press(press_id, target())
    capture = VoiceCaptureId("voice-press-7")

    assert started.effects == (StartVoiceCapture(capture, "zh-TW"),)
    assert controller.request_release_for_press(ShortcutPressId(6)).ignored is True
    assert controller.request_release_for_press(press_id).effects == (StopVoiceCapture(capture),)


def test_watchdog_cancels_only_the_capture_bound_to_its_press() -> None:
    controller = ready_controller()
    press_id = ShortcutPressId(7)
    capture = VoiceCaptureId("voice-press-7")
    controller.request_capture_for_press(press_id, target())

    transition = controller.expire_capture_watchdog(press_id)

    assert transition.effects == (CancelVoiceCapture(capture),)
    assert "release was not received" in transition.projection.message
    assert controller.expire_capture_watchdog(ShortcutPressId(8)).ignored is True


def test_workflow_close_cancels_only_its_active_capture() -> None:
    controller = ready_controller()
    capture = VoiceCaptureId("capture-1")
    controller.request_capture(capture, target())

    assert controller.cancel_capture_for_workflow("other").ignored is True
    assert controller.cancel_capture_for_workflow("workflow-1").effects == (CancelVoiceCapture(capture),)


def test_terminal_applies_ordered_final_segments_once() -> None:
    controller = ready_controller()
    capture = VoiceCaptureId("capture-1")
    frozen_target = target()
    controller.request_capture(capture, frozen_target)
    controller.observe_engine(VoiceEngineFinalSegment(capture, 1, "world"))
    controller.observe_engine(VoiceEngineFinalSegment(capture, 0, "hello"))
    controller.request_stop(capture)

    terminal = controller.observe_engine(VoiceEngineEnded(capture))

    assert terminal.effects == (FinalizeVoiceDraft(capture, frozen_target, "hello world"),)
    assert controller.observe_engine(VoiceEngineEnded(capture)).ignored is True


def test_natural_end_before_release_restarts_only_the_same_capture() -> None:
    controller = ready_controller()
    capture = VoiceCaptureId("capture-1")
    controller.request_capture(capture, target())
    controller.observe_engine(VoiceEngineFinalSegment(capture, 0, "first"))

    restarted = controller.observe_engine(VoiceEngineEnded(capture))

    assert restarted.effects == (StartVoiceCapture(capture, "zh-TW", 1),)


def test_end_before_listening_settles_instead_of_restarting_microphone_permission() -> None:
    controller = ready_controller()
    capture = VoiceCaptureId("capture-1")
    frozen_target = target()
    controller.request_capture(capture, frozen_target)

    terminal = controller.observe_engine(VoiceEngineEnded(capture))

    assert terminal.effects == (
        RestoreVoiceReview(frozen_target, "Voice Input stopped before the microphone was ready. Try again."),
    )
    assert controller.projection.capture_id is None


def test_cancel_discards_provisional_and_finalized_capture_content() -> None:
    controller = ready_controller()
    capture = VoiceCaptureId("capture-1")
    controller.request_capture(capture, target())
    controller.observe_engine(VoiceEngineFinalSegment(capture, 0, "discard me"))

    assert controller.request_cancel(capture).effects == (CancelVoiceCapture(capture),)
    assert controller.observe_engine(VoiceEngineEnded(capture)).effects[0].message == "Voice Input cancelled."
    assert controller.projection.capture_id is None


def test_conflicting_duplicate_segment_fails_the_capture() -> None:
    controller = ready_controller()
    capture = VoiceCaptureId("capture-1")
    controller.request_capture(capture, target())
    controller.observe_engine(VoiceEngineFinalSegment(capture, 0, "first"))

    transition = controller.observe_engine(VoiceEngineFinalSegment(capture, 0, "different"))

    assert transition.effects[0].message == "Voice Input received an invalid recognition response."
    assert controller.projection.capture_id is None
    assert "invalid recognition response" in controller.projection.message


def test_language_changes_apply_only_between_captures() -> None:
    controller = ready_controller()
    change = VoiceLanguageChangeId("language-1")
    transition = controller.set_language(VoiceLanguage("en-US"), change)
    assert transition.effects == (PersistVoiceLanguage(change, "en-US"),)
    assert controller.complete_language_save(change).projection.language == "en-US"
    capture = VoiceCaptureId("capture-1")
    controller.request_capture(capture, target())
    assert controller.set_language(VoiceLanguage("zh-TW"), VoiceLanguageChangeId("language-2")).ignored is True


def test_disable_rejects_new_captures_and_waits_for_both_identity_scoped_joins() -> None:
    controller = ready_controller()
    capture = VoiceCaptureId("capture-1")
    controller.request_capture(capture, target())
    disable = VoiceDisableId("disable-1")

    transition = controller.request_disable(disable)

    assert transition.effects == (
        CancelVoiceCapture(capture),
        ShutdownVoiceEngine(disable),
        PersistVoiceDisabled(disable),
    )
    assert controller.request_capture(VoiceCaptureId("capture-2"), target()).ignored is True
    assert controller.complete_disable_shutdown(VoiceDisableId("old")).ignored is True
    assert controller.complete_disable_preference(disable).projection.capability is VoiceCapabilityPhase.DISABLING
    assert controller.complete_disable_shutdown(disable).projection.capability is VoiceCapabilityPhase.DISABLED


def test_disable_preference_failure_remains_explicitly_retriable() -> None:
    controller = ready_controller()
    disable = VoiceDisableId("disable-1")
    controller.request_disable(disable)
    controller.complete_disable_shutdown(disable)

    transition = controller.complete_disable_preference(disable, "disk unavailable")

    assert transition.projection.capability is VoiceCapabilityPhase.DISABLE_FAILED
