from __future__ import annotations

from pathlib import Path

from clipai.core.event_bus import EventBus
from clipai.platform.tts_service import TTSService


def test_tts_service_uses_callback_lifecycle_when_supported() -> None:
    bus = EventBus()
    seen: list[tuple[bool, str]] = []
    bus.subscribe("tts_state", lambda payload: seen.append((payload["is_speaking"], payload["phase"])))

    def speak_fn(text: str, *, on_request=None, on_buffering=None, on_start=None, on_end=None) -> None:
        assert text == "hello"
        if on_request:
            on_request()
        if on_buffering:
            on_buffering()
        if on_start:
            on_start()
        if on_end:
            on_end()

    service = TTSService(bus, speak_fn)
    service.speak("hello")

    assert seen == [
        (True, "requesting"),
        (True, "buffering"),
        (True, "start"),
        (False, "end"),
    ]


def test_tts_service_normalizes_markdown_and_symbols_for_speech() -> None:
    service = TTSService(EventBus(), lambda text: None)

    normalized = service._normalize_for_speech(
        """
        * Summary
        - item one
        [ClipAI](https://example.com)
        (extra) [ ] {meta}
        ```
        print("debug")
        ```
        keep ordinary punctuation, please.
        """
    )

    assert "https://example.com" not in normalized
    assert "print" not in normalized
    assert "*" not in normalized
    assert " - " not in normalized
    assert "[" not in normalized
    assert "]" not in normalized
    assert "ClipAI" in normalized
    assert "keep ordinary punctuation, please." in normalized


def test_tts_service_strips_markdown_heading_hash_but_keeps_meaningful_hash_uses() -> None:
    service = TTSService(EventBus(), lambda text: None)

    normalized = service._normalize_for_speech(
        """
        # Title
        standalone # marker
        C# remains meaningful
        #hashtag can stay
        """
    )

    assert "Title" in normalized
    assert "# Title" not in normalized
    assert "standalone # marker" not in normalized
    assert "C#" in normalized
    assert "#hashtag" in normalized


def test_tts_service_uses_named_normalization_pipeline() -> None:
    content = Path("clipai/platform/tts_service.py").read_text(encoding="utf-8")
    assert "def _normalize_for_speech" in content
    assert "self._strip_fenced_code_blocks" in content
    assert "self._replace_markdown_links" in content
    assert "self._normalize_headings_and_hashes" in content
    assert "self._normalize_bullets_and_dividers" in content
    assert "self._normalize_brackets" in content


def test_tts_voice_mapping_uses_requested_voices() -> None:
    content = Path("clipai/platform/tts.py").read_text(encoding="utf-8")
    assert '"zh-tw": "zh-TW-HsiaoChenNeural"' in content
    assert '"en": "en-US-AndrewMultilingualNeural"' in content
