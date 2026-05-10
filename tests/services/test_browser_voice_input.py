from __future__ import annotations

import requests

from clipai.services.browser_voice_input import (
    BrowserVoiceInputConfig,
    BrowserVoiceInputServer,
    BrowserVoiceInputState,
)


def test_browser_voice_input_state_appends_and_writes_full_text(monkeypatch) -> None:
    writes: list[str] = []
    monkeypatch.setattr("clipai.services.browser_voice_input.write_clipboard_text", writes.append)

    state = BrowserVoiceInputState()

    assert state.append_transcript(" first ") == "first"
    assert state.append_transcript("second") == "first\nsecond"
    assert writes == ["first", "first\nsecond"]


def test_browser_voice_input_server_transcript_api(monkeypatch) -> None:
    writes: list[str] = []
    monkeypatch.setattr("clipai.services.browser_voice_input.write_clipboard_text", writes.append)
    server = BrowserVoiceInputServer(
        BrowserVoiceInputConfig(port=0, auto_start=False),
        state=BrowserVoiceInputState(),
    )

    try:
        url = server.start()
        response = requests.get(url, timeout=3)
        assert response.status_code == 200
        assert "webkitSpeechRecognition" in response.text

        api_base = url.removesuffix("/voice")
        transcript_response = requests.post(
            f"{api_base}/api/transcript",
            json={"text": "hello"},
            timeout=3,
        )
        assert transcript_response.status_code == 200
        assert transcript_response.json() == {"text": "hello"}

        state_response = requests.get(f"{api_base}/api/state", timeout=3)
        assert state_response.json() == {"text": "hello"}
        assert writes == ["hello"]
    finally:
        server.stop()
