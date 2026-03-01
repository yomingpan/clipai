from __future__ import annotations


class ConversationState:
    def __init__(self) -> None:
        self.content = ""
        self.status = "idle"

    def append_content(self, text: str) -> None:
        self.content += text

    def reset(self) -> None:
        self.content = ""
        self.status = "idle"
