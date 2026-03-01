from __future__ import annotations

from ClipAI.core.constants import EVENT_MEMORY_CHANGE


class MemoryManager:
    def __init__(self, event_bus) -> None:
        self._event_bus = event_bus
        self._manual: list[str] = []
        self._auto: list[str] = []

    def add_manual(self, item: str) -> None:
        self._manual.append(item)
        self._publish()

    def add_auto(self, item: str) -> None:
        self._auto.append(item)
        self._publish()

    def _publish(self) -> None:
        self._event_bus.publish(
            EVENT_MEMORY_CHANGE,
            {"manual_count": len(self._manual), "auto_count": len(self._auto)},
        )
