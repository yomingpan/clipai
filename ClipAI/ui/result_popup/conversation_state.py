from __future__ import annotations

from clipai.ui.result_popup.popup_session import PopupSession


class ConversationState:
    def __init__(self) -> None:
        self.content = ""
        self.status = "idle"
        self.session: PopupSession | None = None

    def append_content(self, text: str) -> None:
        self.content += text

    def reset(self) -> None:
        self.content = ""
        self.status = "idle"
        self.session = None

    def bind_session(self, session: PopupSession) -> None:
        self.session = session
        self.content = session.latest_result
