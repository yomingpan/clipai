from __future__ import annotations

import tkinter as tk
from typing import Callable

from clipai.platform.clipboard import write_clipboard_text
from clipai.services.archive_service import ArchiveService
from clipai.services.popup_session import PopupSession


class PopupActionHandler:
    def __init__(
        self,
        *,
        archive_service: ArchiveService | None = None,
        tts_service=None,
        clipboard_writer: Callable[[str], None] = write_clipboard_text,
    ) -> None:
        self._archive_service = archive_service or ArchiveService()
        self._tts_service = tts_service
        self._clipboard_writer = clipboard_writer

    @staticmethod
    def selected_output_or_full(text_widget: tk.Text | None, session: PopupSession) -> str:
        if text_widget is not None:
            try:
                selection = text_widget.get("sel.first", "sel.last").strip()
            except tk.TclError:
                selection = ""
            if selection:
                return selection
        return session.render_full_text()

    def copy_output(self, text_widget: tk.Text | None, session: PopupSession) -> bool:
        payload = self.selected_output_or_full(text_widget, session)
        self._clipboard_writer(payload)
        return True

    def archive_output(self, text_widget: tk.Text | None, session: PopupSession) -> bool:
        payload = self.selected_output_or_full(text_widget, session)
        self._archive_service.append_text(session, payload)
        return True

    def toggle_speak(self, text_widget: tk.Text | None, session: PopupSession) -> bool | None:
        if self._tts_service is None:
            return None
        content = self.selected_output_or_full(text_widget, session)
        if self._tts_service.is_speaking():
            self._tts_service.stop()
            return False
        self._tts_service.speak_async(content)
        return True

    def is_speaking(self) -> bool:
        if self._tts_service is None:
            return False
        return bool(self._tts_service.is_speaking())
