from __future__ import annotations

import contextlib
import threading
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable

from clipai.core import constants

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

    def set_tk_root(self, root) -> None:
        self.bind_ui_dispatcher(lambda cb: root.after(0, cb))

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

    def emit(self, event_name: str, /, **payload: Any) -> None:
        self.publish(event_name, payload)

    @contextlib.contextmanager
    def scope_subscribe(self, event_name: str, callback: Subscriber, *, on_ui_thread: bool = False):
        sid = self.subscribe(event_name, callback, on_ui_thread=on_ui_thread)
        try:
            yield sid
        finally:
            self.unsubscribe(sid)

    @contextlib.contextmanager
    def scoped_subscription(self, event_name: str, callback: Subscriber, *, on_ui_thread: bool = False):
        with self.scope_subscribe(event_name, callback, on_ui_thread=on_ui_thread) as sid:
            yield sid


_default_bus: EventBus | None = None
_default_bus_lock = threading.Lock()


def get_event_bus() -> EventBus:
    global _default_bus
    with _default_bus_lock:
        if _default_bus is None:
            _default_bus = EventBus()
        return _default_bus


class Events:
    ACTION_START = constants.EVENT_ACTION_START
    ACTION_COMPLETE = constants.EVENT_ACTION_COMPLETE
    STREAM_COMPLETE = constants.EVENT_ACTION_COMPLETE
    ACTION_ERROR = constants.EVENT_ACTION_ERROR
    PIPELINE_UPDATE = constants.EVENT_PIPELINE_UPDATE
    UI_STATUS = constants.EVENT_UI_STATUS
    TTS_STATE = constants.EVENT_TTS_STATE
    RHYTHM_UPDATE = constants.EVENT_RHYTHM_UPDATE
    RHYTHM_MODE_CHANGE = constants.EVENT_RHYTHM_MODE_CHANGE
    RHYTHM_REMINDER = constants.EVENT_RHYTHM_REMINDER
    MEMORY_CHANGED = constants.EVENT_MEMORY_CHANGE
    FOLLOW_UP_REQUEST = constants.EVENT_FOLLOW_UP_REQUEST
    RHYTHM_ACKNOWLEDGED = "rhythm_acknowledged"
