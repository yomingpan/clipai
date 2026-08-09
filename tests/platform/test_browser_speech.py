from __future__ import annotations

from ClipAI.core.voice import VoiceEngineEnded, VoiceEngineFailed, VoiceEngineFinalSegment, VoiceEngineSetupReady, VoiceTransportFailure
from ClipAI.platform.browser_speech import BrowserSpeechWebView2Engine, VOICE_PROTOCOL_VERSION, _decode_event


def test_protocol_decoder_requires_the_current_version_and_operation_identity() -> None:
    event = _decode_event('{"version": 1, "kind": "setup_ready", "setup_id": "setup-1"}')

    assert event == VoiceEngineSetupReady("setup-1")
    assert _decode_event('{"version": 2, "kind": "setup_ready", "setup_id": "setup-1"}') is None
    assert _decode_event('{"version": 1, "kind": "final"}') is None


def test_protocol_decoder_preserves_final_segment_order_and_typed_failures() -> None:
    segment = _decode_event('{"version": 1, "kind": "final", "capture_id": "capture-1", "sequence": 2, "text": "hello"}')
    failure = _decode_event('{"version": 1, "kind": "failed", "capture_id": "capture-1", "failure": "timeout"}')

    assert segment == VoiceEngineFinalSegment("capture-1", 2, "hello")
    assert failure is not None and failure.failure is VoiceTransportFailure.TIMEOUT
    assert VOICE_PROTOCOL_VERSION == 1


def test_transport_delivers_only_one_terminal_event_for_a_capture() -> None:
    received = []
    engine = BrowserSpeechWebView2Engine(received.append)
    process = object()
    engine._process = process
    engine._capture_id = "capture-1"

    engine._deliver(process, VoiceEngineFailed("capture-1", VoiceTransportFailure.PROCESS_CRASHED))
    engine._deliver(process, VoiceEngineEnded("capture-1"))

    assert received == [VoiceEngineFailed("capture-1", VoiceTransportFailure.PROCESS_CRASHED)]
