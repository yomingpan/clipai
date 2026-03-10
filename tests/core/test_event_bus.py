from __future__ import annotations

from clipai.core.event_bus import EventBus


def test_subscribe_publish_unsubscribe() -> None:
    bus = EventBus()
    received: list[dict] = []
    sid = bus.subscribe("test", lambda payload: received.append(payload))

    bus.publish("test", {"x": 1})
    bus.unsubscribe(sid)
    bus.publish("test", {"x": 2})

    assert received == [{"x": 1}]


def test_scope_subscribe_auto_unsubscribe() -> None:
    bus = EventBus()
    received: list[dict] = []

    with bus.scope_subscribe("test", lambda payload: received.append(payload)):
        bus.publish("test", {"x": 1})

    bus.publish("test", {"x": 2})
    assert received == [{"x": 1}]


def test_ui_dispatcher_delivery() -> None:
    bus = EventBus()
    callbacks: list[callable] = []
    out: list[int] = []
    bus.bind_ui_dispatcher(lambda cb: callbacks.append(cb))
    bus.subscribe("u", lambda payload: out.append(payload["v"]), on_ui_thread=True)

    bus.publish("u", {"v": 7})
    assert out == []
    assert len(callbacks) == 1

    callbacks[0]()
    assert out == [7]
