from __future__ import annotations

from ClipAI.core.voice import VoiceEngineEnded, VoiceEngineFailed, VoiceEngineFinalSegment, VoiceEngineSetupFailed, VoiceEngineSetupReady, VoiceTransportFailure
from ClipAI.platform.browser_speech import BrowserSpeechWebView2Engine, VOICE_PROTOCOL_VERSION, _decode_event


class BrokenInput:
    def write(self, _value) -> None:
        raise BrokenPipeError()

    def flush(self) -> None:
        raise AssertionError("flush must not run after a broken write")


class BrokenProcess:
    def __init__(self) -> None:
        self.stdin = BrokenInput()
        self.stdout = None
        self.terminated = 0

    def poll(self): return None
    def terminate(self) -> None: self.terminated += 1


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


def test_capture_write_failure_settles_once_and_discards_the_broken_host() -> None:
    received = []
    process = BrokenProcess()
    engine = BrowserSpeechWebView2Engine(received.append)
    engine._process = process
    engine._capture_id = "capture-1"

    engine.stop_capture("capture-1")
    engine.cancel_capture("capture-1")

    assert received == [VoiceEngineFailed("capture-1", VoiceTransportFailure.PROCESS_CRASHED)]
    assert process.terminated == 1
    assert engine._process is None


def test_setup_write_failure_is_typed_and_does_not_leave_a_live_setup() -> None:
    received = []
    process = BrokenProcess()
    engine = BrowserSpeechWebView2Engine(received.append)
    engine._process = process

    engine.prepare("setup-1", "zh-TW")

    assert received == [VoiceEngineSetupFailed("setup-1", VoiceTransportFailure.INITIALIZATION_FAILED)]
    assert process.terminated == 1
    assert engine._process is None
