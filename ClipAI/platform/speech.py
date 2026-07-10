from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import threading
import time


class EdgeSpeechOutput:
    """Blocking speech adapter intended to run inside TaskSupervisor."""

    def __init__(self, *, voice: str, rate: str = "+0%", volume: str = "+0%") -> None:
        self._voice = voice
        self._rate = rate
        self._volume = volume
        self._stop = threading.Event()

    def speak(self, text: str) -> None:
        import edge_tts
        import pygame

        self._stop.clear()
        path = Path(tempfile.gettempdir()) / f"clipai-speech-{threading.get_ident()}.mp3"
        try:
            communicate = edge_tts.Communicate(text, self._voice, rate=self._rate, volume=self._volume)
            asyncio.run(communicate.save(str(path)))
            if self._stop.is_set():
                return
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy() and not self._stop.wait(0.05):
                pass
            if self._stop.is_set():
                pygame.mixer.music.stop()
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

