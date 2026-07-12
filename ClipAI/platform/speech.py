from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import threading

from ClipAI.core.models import SpeechRequest


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
                communicate = edge_tts.Communicate(request.text, voice, rate=self._rate, volume=self._volume)
                asyncio.run(communicate.save(str(path)))
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

