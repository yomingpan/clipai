from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from uuid import uuid4

from clipai.context.clipboard_session import ClipboardSession
from clipai.platform.clipboard import read_clipboard_text, write_clipboard_text

logger = logging.getLogger("clipai.input")


@dataclass(frozen=True)
class InputResolution:
    text: str
    source: str
    error: str | None = None


class InputResolver:
    def __init__(
        self,
        *,
        copy_delay_sec: float = 0.2,
        poll_count: int = 50,
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
            sentinel = self._selection_sentinel()
            write_clipboard_text(sentinel, retries=1, delay=0)
            logger.info("[clipai] Selection capture start: sentinel written")
            time.sleep(self._copy_delay_sec)

            keyboard = pynput_keyboard.Controller()
            keyboard.press(pynput_keyboard.Key.ctrl)
            keyboard.press("c")
            keyboard.release("c")
            keyboard.release(pynput_keyboard.Key.ctrl)

            for poll_index in range(self._poll_count):
                time.sleep(self._poll_delay_sec)
                current = read_clipboard_text(retries=1, delay=0) or ""
                if current == sentinel and poll_index in {0, 4, 9, self._poll_count - 1}:
                    logger.info(
                        "[clipai] Selection capture poll=%s/%s clipboard still sentinel",
                        poll_index + 1,
                        self._poll_count,
                    )
                if current and current != sentinel:
                    logger.info(
                        "[clipai] Selection capture success: poll=%s chars=%s",
                        poll_index + 1,
                        len(current.strip()),
                    )
                    return current.strip()
            logger.warning("[clipai] Selection capture failed: clipboard stayed at sentinel")
            return ""

    @staticmethod
    def _selection_sentinel() -> str:
        return f"__CLIPAI_SELECTION_SENTINEL__:{uuid4()}__"

    @staticmethod
    def _prompt_for_text() -> str:
        try:
            return input("No highlighted text or clipboard content found. Enter text: ").strip()
        except EOFError:
            return ""
