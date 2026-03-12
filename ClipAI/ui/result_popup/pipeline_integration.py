from __future__ import annotations

from clipai.core.constants import (
    EVENT_ACTION_COMPLETE,
    EVENT_ACTION_ERROR,
    EVENT_ACTION_START,
    EVENT_PIPELINE_UPDATE,
    EVENT_TTS_STATE,
)
from clipai.ui.result_popup.conversation_state import ConversationState
from clipai.ui.result_popup.stream_managers import StreamManager


class PipelineIntegration:
    def __init__(self, event_bus, popup, state: ConversationState) -> None:
        self._event_bus = event_bus
        self._popup = popup
        self._state = state
        self._stream_manager = StreamManager(state)

    def start(self) -> list[str]:
        return [
            self._event_bus.subscribe(EVENT_ACTION_START, self._on_action_start, on_ui_thread=True),
            self._event_bus.subscribe(EVENT_PIPELINE_UPDATE, self._on_pipeline_update, on_ui_thread=True),
            self._event_bus.subscribe(EVENT_ACTION_COMPLETE, self._on_action_complete, on_ui_thread=True),
            self._event_bus.subscribe(EVENT_ACTION_ERROR, self._on_action_error, on_ui_thread=True),
            self._event_bus.subscribe(EVENT_TTS_STATE, self._on_tts_state, on_ui_thread=True),
        ]

    def _on_action_start(self, payload: dict) -> None:
        del payload
        self._state.reset()
        self._state.status = "processing"
        self._popup.show()
        self._popup.set_content("")

    def _on_pipeline_update(self, payload: dict) -> None:
        self._stream_manager.apply_chunk(str(payload.get("content", "")))
        self._popup.set_content(self._state.content)

    def _on_action_complete(self, payload: dict) -> None:
        del payload
        self._state.status = "success"

    def _on_action_error(self, payload: dict) -> None:
        msg = str(payload.get("message", "unknown error"))
        self._state.status = "error"
        self._popup.set_content(self._state.content + "\n\n[ERROR] " + msg)

    def _on_tts_state(self, payload: dict) -> None:
        del payload
