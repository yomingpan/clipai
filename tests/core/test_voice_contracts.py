from __future__ import annotations

import pytest

from ClipAI.core.commands import AppCommand, EnableVoiceInput, VoiceEngineEventReceived
from ClipAI.core.voice import (
    SUPPORTED_VOICE_LANGUAGES,
    VoiceCaptureId,
    VoiceCapturePhase,
    VoiceCapabilityPhase,
    VoiceEngineFinalSegment,
    VoiceEngineSetupReady,
    VoiceDraftInsertion,
    VoiceLanguage,
    VoiceOrigin,
    VoiceSetupId,
)


def test_voice_identities_are_distinct_immutable_values() -> None:
    setup_id = VoiceSetupId("setup-1")
    capture_id = VoiceCaptureId("capture-1")

    assert setup_id == "setup-1"
    assert capture_id == "capture-1"
    assert setup_id != capture_id


def test_only_v1_languages_are_supported() -> None:
    assert SUPPORTED_VOICE_LANGUAGES == ("zh-TW", "en-US")
    assert VoiceLanguage("zh-TW") == "zh-TW"
    with pytest.raises(ValueError, match="unsupported Voice Input language"):
        VoiceLanguage("ja-JP")


def test_engine_events_are_identity_scoped_and_immutable() -> None:
    setup_event = VoiceEngineSetupReady(VoiceSetupId("setup-1"))
    segment = VoiceEngineFinalSegment(VoiceCaptureId("capture-1"), 0, "hello")

    assert setup_event.setup_id == "setup-1"
    assert segment.sequence == 0
    with pytest.raises(AttributeError):
        segment.text = "changed"  # type: ignore[misc]


def test_voice_phases_do_not_use_free_form_strings() -> None:
    assert VoiceCapabilityPhase.READY.value == "ready"
    assert VoiceCapturePhase.FINALIZING.value == "finalizing"


def test_voice_commands_are_part_of_the_typed_application_command_union() -> None:
    setup = EnableVoiceInput(VoiceSetupId("setup-1"))
    event = VoiceEngineEventReceived(VoiceEngineSetupReady(VoiceSetupId("setup-1")))

    assert isinstance(setup, AppCommand)
    assert isinstance(event, AppCommand)


def test_voice_origin_rejects_an_insertion_outside_its_canonical_text() -> None:
    with pytest.raises(ValueError, match="exceeds the Voice Draft"):
        VoiceOrigin(None, "short", 1, VoiceDraftInsertion(4, 0, 6))
