from __future__ import annotations

from clipai.core.constants import EVENT_RHYTHM_REMINDER, EVENT_RHYTHM_UPDATE
from clipai.core.event_bus import EventBus


class RhythmGuard:
    def __init__(self, event_bus: EventBus, reminder_tempo: float = 120.0) -> None:
        self._event_bus = event_bus
        self._reminder_tempo = reminder_tempo
        self._event_bus.subscribe(EVENT_RHYTHM_UPDATE, self._on_rhythm_update)

    def _on_rhythm_update(self, payload: dict) -> None:
        tempo = float(payload.get("tempo", 0.0))
        if tempo > self._reminder_tempo:
            self._event_bus.publish(
                EVENT_RHYTHM_REMINDER,
                {
                    "reason": "tempo_too_high",
                    "state": str(payload.get("state", "unknown")),
                },
            )
