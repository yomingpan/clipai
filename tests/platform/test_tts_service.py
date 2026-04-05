from __future__ import annotations

from clipai.core.event_bus import EventBus
from clipai.platform.tts_service import TTSService


def test_tts_service_uses_callback_lifecycle_when_supported() -> None:
    bus = EventBus()
    seen: list[tuple[bool, str]] = []
    bus.subscribe("tts_state", lambda payload: seen.append((payload["is_speaking"], payload["phase"])))

    def speak_fn(text: str, *, on_start=None, on_end=None) -> None:
        assert text == "hello"
        if on_start:
            on_start()
        if on_end:
            on_end()

    service = TTSService(bus, speak_fn)
    service.speak("hello")

    assert seen == [(True, "start"), (False, "end")]
