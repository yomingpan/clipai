from __future__ import annotations

import re
import threading
import time
from typing import Callable

from clipai.core.constants import EVENT_TTS_STATE
from clipai.core.event_bus import EventBus


class TTSService:
    def __init__(self, event_bus: EventBus, speak_fn: Callable[[str], None]) -> None:
        self._event_bus = event_bus
        self._speak_fn = speak_fn

    def _clean_markdown(self, text: str) -> str:
        text = re.sub(r"```[\s\S]*?```", "", text)
        text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", text)
        return text.strip()

    def speak(self, text: str, cancellation_token=None) -> None:
        cleaned = self._clean_markdown(text)
        self._event_bus.publish(EVENT_TTS_STATE, {"is_speaking": True, "phase": "start"})
        try:
            for _ in range(2):
                if cancellation_token and cancellation_token.is_cancelled():
                    self._event_bus.publish(EVENT_TTS_STATE, {"is_speaking": False, "phase": "stop"})
                    return
                time.sleep(0.01)
            self._speak_fn(cleaned)
            self._event_bus.publish(EVENT_TTS_STATE, {"is_speaking": False, "phase": "end"})
        except Exception:
            self._event_bus.publish(EVENT_TTS_STATE, {"is_speaking": False, "phase": "error"})
            raise

    def speak_async(self, text: str, cancellation_token=None) -> threading.Thread:
        t = threading.Thread(target=self.speak, args=(text, cancellation_token), daemon=True)
        t.start()
        return t
