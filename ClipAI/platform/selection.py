from __future__ import annotations

from collections.abc import Callable
import time
import uuid

from ClipAI.core.ports import ClipboardReader, ClipboardWriter


class SystemSelectionReader:
    """Capture the active selection via Ctrl+C and restore the clipboard."""

    def __init__(
        self,
        clipboard: ClipboardReader | ClipboardWriter,
        *,
        copy_selection: Callable[[], None] | None = None,
        timeout_sec: float = 0.35,
        poll_sec: float = 0.02,
    ) -> None:
        self._clipboard = clipboard
        self._copy_selection = copy_selection or _send_copy_shortcut
        self._timeout_sec = timeout_sec
        self._poll_sec = poll_sec

    def read_text(self) -> str:
        original = self._clipboard.read_text()
        marker = f"__CLIPAI_SELECTION_{uuid.uuid4().hex}__"
        try:
            self._clipboard.write_text(marker)
            self._copy_selection()
            deadline = time.monotonic() + self._timeout_sec
            while time.monotonic() < deadline:
                value = self._clipboard.read_text()
                if value != marker:
                    return value.strip()
                time.sleep(self._poll_sec)
            return ""
        except Exception:
            return ""
        finally:
            try:
                self._clipboard.write_text(original)
            except Exception:
                pass


class NoopSelectionReader:
    def read_text(self) -> str:
        return ""


def _send_copy_shortcut() -> None:
    from pynput.keyboard import Controller, Key

    keyboard = Controller()
    with keyboard.pressed(Key.ctrl):
        keyboard.press("c")
        keyboard.release("c")

