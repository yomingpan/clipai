from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import threading
import edge_tts.communicate as _edge_communicate
from edge_tts.constants import TRUSTED_CLIENT_TOKEN

from ClipAI.core.models import SpeechRequest


LEGACY_EDGE_TTS_WSS_URL = _edge_communicate.WSS_URL
EDGE_TTS_WSS_URL = (
    "wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1"
    f"?Ocp-Apim-Subscription-Key={TRUSTED_CLIENT_TOKEN}"
)
_EDGE_ENDPOINT_LOCK = threading.Lock()


class EdgeSpeechOutput:
    """Blocking speech adapter intended to run inside TaskSupervisor."""

    def __init__(self, *, voice: str, rate: str = "+0%", volume: str = "+0%") -> None:
        self._voice = voice
        self._rate = rate
        self._volume = volume
        self._stop = threading.Event()
        self._playback_lock = threading.Lock()

    def speak(self, request: SpeechRequest) -> None:
        import edge_tts
        import pygame

        with self._playback_lock:
            if request.cancellation.is_cancelled:
                return
            self._stop.clear()
            path = Path(tempfile.gettempdir()) / f"clipai-speech-{threading.get_ident()}.mp3"
            try:
                voice = request.voice_override or self._voice
                # This dependency reads a module-global URL while streaming.
                # Serialize that narrow boundary across all adapter instances,
                # keep the import-time fallback, and restore even on exceptions.
                with _EDGE_ENDPOINT_LOCK:
                    previous_url = _edge_communicate.WSS_URL
                    try:
                        for endpoint in (EDGE_TTS_WSS_URL, LEGACY_EDGE_TTS_WSS_URL):
                            if self._stop.is_set() or request.cancellation.is_cancelled:
                                return
                            _edge_communicate.WSS_URL = endpoint
                            communicate = edge_tts.Communicate(
                                request.text, voice,
                                rate=request.rate_override or self._rate,
                                volume=self._volume,
                            )
                            try:
                                asyncio.run(communicate.save(str(path)))
                            except Exception as exc:
                                if endpoint != EDGE_TTS_WSS_URL or getattr(exc, "status", None) != 403:
                                    raise
                            else:
                                break
                    finally:
                        _edge_communicate.WSS_URL = previous_url
                if self._stop.is_set() or request.cancellation.is_cancelled:
                    return
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                pygame.mixer.music.load(str(path))
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    if self._stop.wait(0.05) or request.cancellation.is_cancelled:
                        pygame.mixer.music.stop()
                        break
            finally:
                try:
                    pygame.mixer.music.unload()
                except Exception:
                    pass
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass

    def stop(self) -> None:
        self._stop.set()
        try:
            import pygame

            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception:
            pass

