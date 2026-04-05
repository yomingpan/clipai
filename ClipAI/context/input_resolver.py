from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from uuid import uuid4

from clipai.context.clipboard_session import ClipboardSession
from clipai.logging_setup import diagnostics_enabled
from clipai.platform.clipboard import image_to_base64, read_clipboard_image, read_clipboard_text, write_clipboard_text

logger = logging.getLogger("clipai.input")


@dataclass(frozen=True)
class InputResolution:
    text: str
    source: str
    image_base64: str | None = None
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
        selection_modes = {"selection_or_clipboard", "selection_or_clipboard_image", "selection"}
        clipboard_text_modes = {"selection_or_clipboard", "selection_or_clipboard_image", "clipboard", "clipboard_or_image"}
        clipboard_image_modes = {"selection_or_clipboard", "selection_or_clipboard_image", "clipboard_image", "clipboard_or_image"}

        if self._enable_selection_capture and normalized_mode in selection_modes:
            selected = self._read_selected_text()
            if selected:
                return InputResolution(text=selected, source="selection")
            if normalized_mode == "selection":
                return InputResolution(text="", source="empty", error="No highlighted text was found.")

        if normalized_mode in clipboard_text_modes:
            clipboard_text = (read_clipboard_text() or "").strip()
            if clipboard_text:
                return InputResolution(text=clipboard_text, source="clipboard")

        if normalized_mode in clipboard_image_modes:
            image_base64 = self._read_clipboard_image_base64()
            if image_base64:
                return InputResolution(
                    text="[Clipboard image attached]",
                    source="clipboard_image",
                    image_base64=image_base64,
                )

        manual = self._prompt_for_text()
        if manual:
            return InputResolution(text=manual, source="manual")
        return InputResolution(
            text="",
            source="empty",
            error="No highlighted text, clipboard text, or clipboard image was found.",
        )

    def _read_selected_text(self) -> str:
        try:
            from pynput import keyboard as pynput_keyboard
        except ImportError:
            return ""

        with ClipboardSession():
            sentinel = self._selection_sentinel()
            write_clipboard_text(sentinel, retries=1, delay=0)
            logger.debug("[clipai] Selection capture start: sentinel written")
            time.sleep(self._copy_delay_sec)

            keyboard = pynput_keyboard.Controller()
            keyboard.press(pynput_keyboard.Key.ctrl)
            keyboard.press("c")
            keyboard.release("c")
            keyboard.release(pynput_keyboard.Key.ctrl)

            for poll_index in range(self._poll_count):
                time.sleep(self._poll_delay_sec)
                current = read_clipboard_text(retries=1, delay=0) or ""
                if diagnostics_enabled("selection_capture_polls") and current == sentinel and poll_index in {0, 4, 9, self._poll_count - 1}:
                    logger.debug(
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
    def _read_clipboard_image_base64() -> str | None:
        image = read_clipboard_image(retries=1, delay=0)
        if image is None or not hasattr(image, "mode"):
            return None
        try:
            return image_to_base64(image)
        except Exception:
            logger.exception("[clipai] Clipboard image conversion failed.")
            return None

    @staticmethod
    def _selection_sentinel() -> str:
        return f"__CLIPAI_SELECTION_SENTINEL__:{uuid4()}__"

    @staticmethod
    def _prompt_for_text() -> str:
        try:
            return input("No highlighted text or clipboard content found. Enter text: ").strip()
        except EOFError:
            return ""
