from __future__ import annotations

from ClipAI.ui.result_popup.conversation_state import ConversationState


class StreamManager:
    def __init__(self, state: ConversationState) -> None:
        self._state = state

    def apply_chunk(self, chunk: str) -> None:
        self._state.append_content(chunk)
