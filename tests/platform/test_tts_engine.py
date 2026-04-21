from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from clipai.platform.tts import TTSEngine, _QueuedStreamSource


def test_tts_engine_resolves_single_voice_without_fallback(tmp_path: Path) -> None:
    engine = object.__new__(TTSEngine)
    engine.rate = "+0%"
    engine.volume = "+0%"
    engine.proxy = None
    engine.temp_dir = str(tmp_path / "temp")
    engine.cache_dir = str(tmp_path / "cache")
    Path(engine.temp_dir).mkdir(parents=True, exist_ok=True)
    Path(engine.cache_dir).mkdir(parents=True, exist_ok=True)
    engine._stop_event = threading.Event()
    engine._speak_id = 1
    engine._detect_voice = lambda text: "en-US-AndrewMultilingualNeural"

    attempted: list[str] = []

    async def fake_synthesize(text: str, voice: str, output_path: str, speak_id: int):
        attempted.append(voice)
        Path(output_path).write_bytes(b"audio")
        return True

    engine._synthesize_voice_to_path = fake_synthesize

    resolved_path, delete_after = asyncio.run(engine._resolve_audio_path("hello", 1))

    assert attempted == ["en-US-AndrewMultilingualNeural"]
    assert resolved_path is not None
    assert resolved_path.endswith(".mp3")
    assert Path(resolved_path).exists()
    assert delete_after is False


def test_tts_engine_logs_voice_resolution_steps_exist() -> None:
    content = Path("clipai/platform/tts.py").read_text(encoding="utf-8")
    assert "TTS voice resolved by manual mode" in content
    assert "TTS voice resolved by auto detect" in content
    assert "TTS synthesize request" in content


def test_miniaudio_stream_source_exposes_callback_state() -> None:
    source = _QueuedStreamSource(threading.Event())

    assert hasattr(source, "ffi_handle")
    assert hasattr(source, "error_in_readcallback")
    assert source.error_in_readcallback is None
