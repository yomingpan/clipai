from __future__ import annotations

import sys
import threading
import time
from types import SimpleNamespace
import pytest
import edge_tts.communicate as edge_communicate

from ClipAI.core.models import SpeechRequest
from ClipAI.core.state import CancellationToken
from ClipAI.platform.speech import EdgeSpeechOutput
from ClipAI.platform import speech


class Music:
    def load(self, _path: str) -> None:
        pass

    def play(self) -> None:
        pass

    def get_busy(self) -> bool:
        return False

    def stop(self) -> None:
        pass

    def unload(self) -> None:
        pass


def test_edge_speech_uses_the_rate_captured_on_the_request(monkeypatch) -> None:
    calls = []

    class Communicate:
        def __init__(self, text, voice, *, rate, volume) -> None:
            calls.append((text, voice, rate, volume))

        async def save(self, _path: str) -> None:
            pass

    mixer = SimpleNamespace(get_init=lambda: True, init=lambda: None, music=Music())
    monkeypatch.setitem(sys.modules, "edge_tts", SimpleNamespace(Communicate=Communicate))
    monkeypatch.setitem(sys.modules, "pygame", SimpleNamespace(mixer=mixer))
    output = EdgeSpeechOutput(voice="default", rate="+0%")

    output.speak(SpeechRequest("hello", None, CancellationToken(), rate_override="+50%"))

    assert calls == [("hello", "default", "+50%", "+0%")]


def install_fake_speech(monkeypatch, save):
    class Communicate:
        def __init__(self, *args, **kwargs):
            pass
        async def save(self, path):
            save(edge_communicate.WSS_URL)
    monkeypatch.setitem(sys.modules, "edge_tts", SimpleNamespace(Communicate=Communicate))
    monkeypatch.setitem(sys.modules, "pygame", SimpleNamespace(mixer=SimpleNamespace(get_init=lambda: True, music=Music())))


def test_success_then_403_still_falls_back_to_import_time_legacy_endpoint(monkeypatch):
    original = edge_communicate.WSS_URL
    calls = []
    class Forbidden(Exception):
        status = 403
    def save(url):
        calls.append(url)
        if len(calls) == 2:
            raise Forbidden()
    install_fake_speech(monkeypatch, save)
    output = EdgeSpeechOutput(voice="default")
    for _ in range(2):
        output.speak(SpeechRequest("fixture", None, CancellationToken()))
        assert edge_communicate.WSS_URL == original
    assert calls == [speech.EDGE_TTS_WSS_URL, speech.EDGE_TTS_WSS_URL, speech.LEGACY_EDGE_TTS_WSS_URL]


@pytest.mark.parametrize("status", [401, 429, 500, None])
def test_non_403_speech_failure_does_not_fall_back(monkeypatch, status):
    original = edge_communicate.WSS_URL
    calls = []
    class Failure(Exception):
        pass
    error = Failure()
    error.status = status
    def save(url):
        calls.append(url)
        raise error
    install_fake_speech(monkeypatch, save)
    with pytest.raises(Failure):
        EdgeSpeechOutput(voice="default").speak(SpeechRequest("fixture", None, CancellationToken()))
    assert len(calls) == 1
    assert edge_communicate.WSS_URL == original


def test_concurrent_speech_calls_keep_endpoint_scoped_and_restore_global(monkeypatch):
    original = edge_communicate.WSS_URL
    calls = []
    errors = []
    barrier = threading.Barrier(2)
    def save(url):
        time.sleep(0.01)
        assert edge_communicate.WSS_URL == url
        calls.append(url)
    install_fake_speech(monkeypatch, save)
    def speak():
        try:
            barrier.wait(timeout=2)
            EdgeSpeechOutput(voice="default").speak(SpeechRequest("fixture", None, CancellationToken()))
        except Exception as error:
            errors.append(error)
    threads = [threading.Thread(target=speak) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)
    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert calls == [speech.EDGE_TTS_WSS_URL, speech.EDGE_TTS_WSS_URL]
    assert edge_communicate.WSS_URL == original
