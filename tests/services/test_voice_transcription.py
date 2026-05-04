from __future__ import annotations

from clipai.services.voice_transcription import OpenAITranscriptionClient, OpenAITranscriptionConfig


class _Response:
    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, str]:
        return {"text": "hello world"}


def test_openai_transcription_posts_webm_audio(monkeypatch) -> None:
    seen = {}
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fake_post(url, headers, data, files, timeout):
        seen["url"] = url
        seen["headers"] = headers
        seen["data"] = data
        seen["files"] = files
        seen["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("clipai.services.voice_transcription.requests.post", fake_post)

    client = OpenAITranscriptionClient(
        OpenAITranscriptionConfig(model="whisper-1", language="zh", timeout_sec=30)
    )

    assert client.transcribe_webm(b"audio") == "hello world"
    assert seen["url"] == "https://api.openai.com/v1/audio/transcriptions"
    assert seen["headers"] == {"Authorization": "Bearer test-key"}
    assert seen["data"]["model"] == "whisper-1"
    assert seen["data"]["language"] == "zh"
    assert seen["files"]["file"][0] == "speech.webm"
    assert seen["files"]["file"][2] == "audio/webm"
    assert seen["timeout"] == 30


def test_openai_transcription_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = OpenAITranscriptionClient(OpenAITranscriptionConfig())

    try:
        client.transcribe_webm(b"audio")
    except RuntimeError as exc:
        assert "OPENAI_API_KEY" in str(exc)
    else:
        raise AssertionError("Expected missing API key error")
