from __future__ import annotations

from collections import defaultdict
from typing import Callable

EventCallback = Callable[[object], None]
Unsubscribe = Callable[[], None]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventCallback]] = defaultdict(list)

    def subscribe(self, event_name: str, callback: EventCallback) -> Unsubscribe:
        self._subscribers[event_name].append(callback)

        def unsubscribe() -> None:
            subscribers = self._subscribers.get(event_name, [])
            if callback in subscribers:
                subscribers.remove(callback)

        return unsubscribe

    def publish(self, event_name: str, payload: object = None) -> None:
        for callback in list(self._subscribers.get(event_name, [])):
            callback(payload)


_EVENT_BUS = EventBus()


def get_event_bus() -> EventBus:
    return _EVENT_BUS
