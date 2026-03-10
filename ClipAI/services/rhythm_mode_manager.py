from __future__ import annotations

from clipai.core.constants import EVENT_RHYTHM_MODE_CHANGE
from clipai.core.event_bus import EventBus


class RhythmModeManager:
    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._mode = "balanced"
        self._params = {"max_tempo": 80.0, "reminder_threshold": 2.0}

    @property
    def mode(self) -> str:
        return self._mode

    def params(self) -> dict[str, float]:
        return dict(self._params)

    def set_mode(self, mode: str, params: dict[str, float] | None = None) -> None:
        self._mode = mode
        if params:
            self._params.update(params)
        self._event_bus.publish(EVENT_RHYTHM_MODE_CHANGE, {"mode": self._mode, "params": dict(self._params)})
