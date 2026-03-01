from __future__ import annotations

import time
from dataclasses import dataclass

from ClipAI.core.cancellation import CancellationController
from ClipAI.core.constants import EVENT_PIPELINE_UPDATE
from ClipAI.core.event_bus import EventBus


@dataclass(frozen=True)
class PipelineSession:
    session_id: str
    action_id: str


class PipelineCoordinator:
    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._controllers: dict[str, CancellationController] = {}
        self._current_session_id: str | None = None
        self._current_action_id: str | None = None

    @property
    def current_session_id(self) -> str | None:
        return self._current_session_id

    @property
    def current_action_id(self) -> str | None:
        return self._current_action_id

    def start_session(self, session_id: str, action_id: str, *, cancel_previous: bool = True) -> PipelineSession:
        if cancel_previous and self._current_session_id:
            self.cancel_session(self._current_session_id, reason="new session started")
        self._current_session_id = session_id
        self._current_action_id = action_id
        self._controllers[session_id] = CancellationController()
        return PipelineSession(session_id=session_id, action_id=action_id)

    def token_for(self, session_id: str):
        return self._controllers[session_id].token

    def cancel_session(self, session_id: str, reason: str | None = None) -> None:
        ctrl = self._controllers.get(session_id)
        if ctrl:
            ctrl.cancel(reason)

    def publish_update(self, content: str, action_id: str, source_meta: dict | None = None) -> None:
        self._event_bus.publish(
            EVENT_PIPELINE_UPDATE,
            {
                "content": content,
                "source_meta": source_meta or {},
                "action_id": action_id,
                "ts": int(time.time() * 1000),
            },
        )
