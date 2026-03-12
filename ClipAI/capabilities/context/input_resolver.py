from __future__ import annotations

import time
from dataclasses import dataclass

from clipai.platform.clipboard import read_clipboard_text
from clipai.capabilities.context.clipboard_session import ClipboardSession


@dataclass(frozen=True)
class InputResolution:
    text: str
    source: str
    error: str | None = None


class InputResolver:
    def __init__(
        self,
        *,
        copy_delay_sec: float = 0.15,
        poll_count: int = 30,
        poll_delay_sec: float = 0.01,
        enable_selection_capture: bool = True,
    ) -> None:
        self._copy_delay_sec = copy_delay_sec
        self._poll_count = poll_count
        self._poll_delay_sec = poll_delay_sec
        self._enable_selection_capture = enable_selection_capture

    def resolve_text(self, explicit_text: str | None, input_mode: str = "selection_or_clipboard") -> InputResolution:
        text = (explicit_text or "").strip()
        if text:
            return InputResolution(text=text, source="explicit")

        normalized_mode = (input_mode or "selection_or_clipboard").lower()
        if self._enable_selection_capture and normalized_mode in {"selection_or_clipboard", "selection"}:
            selected = self._read_selected_text()
            if selected:
                return InputResolution(text=selected, source="selection")
            if normalized_mode == "selection":
                manual = self._prompt_for_text()
                if manual:
                    return InputResolution(text=manual, source="manual")
                return InputResolution(text="", source="empty", error="No highlighted text was found.")

        clipboard_text = (read_clipboard_text() or "").strip()
        if clipboard_text:
            return InputResolution(text=clipboard_text, source="clipboard")

        manual = self._prompt_for_text()
        if manual:
            return InputResolution(text=manual, source="manual")
        return InputResolution(text="", source="empty", error="No highlighted text or clipboard content was found.")

    def _read_selected_text(self) -> str:
        try:
            from pynput import keyboard as pynput_keyboard
        except ImportError:
            return ""

        with ClipboardSession():
            before = read_clipboard_text(retries=1, delay=0) or ""
            time.sleep(self._copy_delay_sec)

            keyboard = pynput_keyboard.Controller()
            keyboard.press(pynput_keyboard.Key.ctrl)
            keyboard.press("c")
            keyboard.release("c")
            keyboard.release(pynput_keyboard.Key.ctrl)

            for _ in range(self._poll_count):
                time.sleep(self._poll_delay_sec)
                current = read_clipboard_text(retries=1, delay=0) or ""
                if current and current != before:
                    return current.strip()
            return ""

    @staticmethod
    def _prompt_for_text() -> str:
        try:
            return input("No highlighted text or clipboard content found. Enter text: ").strip()
        except EOFError:
            return ""
