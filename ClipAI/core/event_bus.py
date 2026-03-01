from __future__ import annotations

import contextlib
import threading
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable

Subscriber = Callable[[dict[str, Any]], None]
UIDispatcher = Callable[[Callable[[], None]], None]


@dataclass(frozen=True)
class _Subscription:
    id: str
    event_name: str
    callback: Subscriber
    on_ui_thread: bool


class EventBus:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subs_by_event: dict[str, dict[str, _Subscription]] = defaultdict(dict)
        self._ui_dispatcher: UIDispatcher | None = None

    def bind_ui_dispatcher(self, dispatch_fn: UIDispatcher) -> None:
        with self._lock:
            self._ui_dispatcher = dispatch_fn

    def subscribe(self, event_name: str, callback: Subscriber, *, on_ui_thread: bool = False) -> str:
        sub = _Subscription(id=str(uuid.uuid4()), event_name=event_name, callback=callback, on_ui_thread=on_ui_thread)
        with self._lock:
            self._subs_by_event[event_name][sub.id] = sub
        return sub.id

    def unsubscribe(self, subscription_id: str) -> None:
        with self._lock:
            for subs in self._subs_by_event.values():
                if subscription_id in subs:
                    del subs[subscription_id]
                    return

    def publish(self, event_name: str, payload: dict[str, Any]) -> None:
        with self._lock:
            subscriptions = list(self._subs_by_event.get(event_name, {}).values())
            ui_dispatcher = self._ui_dispatcher

        for sub in subscriptions:
            if sub.on_ui_thread:
                if ui_dispatcher is None:
                    raise RuntimeError("UI dispatcher is not bound")
                ui_dispatcher(lambda cb=sub.callback: cb(payload))
            else:
                sub.callback(payload)

    @contextlib.contextmanager
    def scope_subscribe(self, event_name: str, callback: Subscriber, *, on_ui_thread: bool = False):
        sid = self.subscribe(event_name, callback, on_ui_thread=on_ui_thread)
        try:
            yield sid
        finally:
            self.unsubscribe(sid)
