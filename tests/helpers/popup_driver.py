from __future__ import annotations

from dataclasses import dataclass, field

from clipai.services.popup_session import PopupSession
from clipai.ui.result_popup.action_handler import PopupActionHandler


class FakeTextWidget:
    def __init__(self, selection: str = "") -> None:
        self.selection = selection
        self.content = ""

    def get(self, start: str, end: str) -> str:
        if start == "sel.first" and end == "sel.last":
            if not self.selection:
                import tkinter as tk

                raise tk.TclError("no selection")
            return self.selection
        return self.content


@dataclass
class FakeArchiveService:
    calls: list[tuple[str, str]] = field(default_factory=list)

    def append_text(self, session: PopupSession, text: str) -> None:
        self.calls.append((session.session_id, text))


@dataclass
class FakeTTSService:
    speaking: bool = False
    spoken: list[str] = field(default_factory=list)
    stop_calls: int = 0

    def is_speaking(self) -> bool:
        return self.speaking

    def speak_async(self, text: str) -> None:
        self.speaking = True
        self.spoken.append(text)

    def stop(self) -> bool:
        self.speaking = False
        self.stop_calls += 1
        return True


class PopupDriver:
    def __init__(self, session: PopupSession, *, selection: str = "") -> None:
        self.session = session
        self.widget = FakeTextWidget(selection=selection)
        self.copied: list[str] = []
        self.archive_service = FakeArchiveService()
        self.tts_service = FakeTTSService()
        self.handler = PopupActionHandler(
            archive_service=self.archive_service,
            tts_service=self.tts_service,
            clipboard_writer=self.copied.append,
        )

    def copy(self) -> bool:
        return self.handler.copy_output(self.widget, self.session)

    def archive(self) -> bool:
        return self.handler.archive_output(self.widget, self.session)

    def toggle_speak(self) -> bool | None:
        return self.handler.toggle_speak(self.widget, self.session)
