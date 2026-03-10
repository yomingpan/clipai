from __future__ import annotations

from clipai.core.event_bus import EventBus


class EventLogger:
    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self.records: list[tuple[str, dict]] = []

    def subscribe(self, event_names: list[str]) -> list[str]:
        ids: list[str] = []
        for name in event_names:
            ids.append(self._event_bus.subscribe(name, lambda payload, n=name: self.records.append((n, payload))))
        return ids
