from __future__ import annotations

import contextlib
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Iterator


Subscriber = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class EventRecord:
    name: str
    payload: dict[str, Any]


class FakeEventBus:
    def __init__(self) -> None:
        self.records: list[EventRecord] = []
        self._subscriptions: dict[str, dict[str, Subscriber]] = defaultdict(dict)
        self._next_id = 0

    def publish(self, event_name: str, payload: dict[str, Any]) -> None:
        self.records.append(EventRecord(event_name, dict(payload)))
        for callback in list(self._subscriptions.get(event_name, {}).values()):
            callback(dict(payload))

    def emit(self, event_name: str, /, **payload: Any) -> None:
        self.publish(event_name, payload)

    def subscribe(self, event_name: str, callback: Subscriber, *, on_ui_thread: bool = False) -> str:
        del on_ui_thread
        self._next_id += 1
        subscription_id = f"fake-sub-{self._next_id}"
        self._subscriptions[event_name][subscription_id] = callback
        return subscription_id

    def unsubscribe(self, subscription_id: str) -> None:
        for subscriptions in self._subscriptions.values():
            subscriptions.pop(subscription_id, None)

    @contextlib.contextmanager
    def scope_subscribe(
        self,
        event_name: str,
        callback: Subscriber,
        *,
        on_ui_thread: bool = False,
    ) -> Iterator[str]:
        subscription_id = self.subscribe(event_name, callback, on_ui_thread=on_ui_thread)
        try:
            yield subscription_id
        finally:
            self.unsubscribe(subscription_id)

    scoped_subscription = scope_subscribe

    def payloads_for(self, event_name: str) -> list[dict[str, Any]]:
        return [record.payload for record in self.records if record.name == event_name]
