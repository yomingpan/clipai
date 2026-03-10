from __future__ import annotations

import statistics
import time
from collections import deque

from clipai.core.constants import EVENT_RHYTHM_UPDATE
from clipai.core.event_bus import EventBus


class RhythmTracker:
    def __init__(self, event_bus: EventBus, window_size: int = 20) -> None:
        self._event_bus = event_bus
        self._timestamps: deque[float] = deque(maxlen=window_size)

    def record_hotkey(self) -> None:
        now = time.time()
        self._timestamps.append(now)
        intervals = [
            self._timestamps[i] - self._timestamps[i - 1]
            for i in range(1, len(self._timestamps))
        ]
        tempo = 0.0 if not intervals else 60.0 / max(0.001, statistics.mean(intervals))
        state = "steady" if len(intervals) >= 3 else "warming"
        self._event_bus.publish(
            EVENT_RHYTHM_UPDATE,
            {
                "tempo": tempo,
                "state": state,
                "metrics": {"count": len(self._timestamps), "mean_interval": statistics.mean(intervals) if intervals else 0.0},
            },
        )
