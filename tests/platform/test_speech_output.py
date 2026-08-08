from __future__ import annotations

import sys
from types import SimpleNamespace

from ClipAI.core.models import SpeechRequest
from ClipAI.core.state import CancellationToken
from ClipAI.platform.speech import EdgeSpeechOutput


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
