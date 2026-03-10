from __future__ import annotations

from clipai.core.constants import EVENT_ACTION_COMPLETE, EVENT_ACTION_START, EVENT_PIPELINE_UPDATE
from clipai.core.event_bus import EventBus
from clipai.ui.result_popup.conversation_state import ConversationState
from clipai.ui.result_popup.pipeline_integration import PipelineIntegration


class _Popup:
    def __init__(self) -> None:
        self.shown = False
        self.content = ""

    def show(self) -> None:
        self.shown = True

    def set_content(self, content: str) -> None:
        self.content = content


def test_pipeline_integration_smoke() -> None:
    bus = EventBus()
    queued = []
    bus.bind_ui_dispatcher(lambda cb: queued.append(cb))

    popup = _Popup()
    state = ConversationState()
    integration = PipelineIntegration(bus, popup, state)
    integration.start()

    bus.publish(EVENT_ACTION_START, {"action_id": "a1", "action_name": "x", "mode": "m", "ts": 1})
    bus.publish(EVENT_PIPELINE_UPDATE, {"content": "hello", "source_meta": {}, "action_id": "a1", "ts": 2})
    bus.publish(EVENT_ACTION_COMPLETE, {"action_id": "a1", "summary": "ok", "duration_ms": 1, "ts": 3})

    for cb in queued:
        cb()

    assert popup.shown is True
    assert "hello" in popup.content
    assert state.status == "success"
