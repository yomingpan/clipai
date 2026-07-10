from __future__ import annotations

from ClipAI.platform.selection import SystemSelectionReader


class Clipboard:
    def __init__(self, value: str) -> None:
        self.value = value
        self.writes: list[str] = []

    def read_text(self) -> str:
        return self.value

    def write_text(self, text: str) -> None:
        self.value = text
        self.writes.append(text)


def test_selection_capture_restores_original_clipboard() -> None:
    clipboard = Clipboard("original")

    def copy_selection() -> None:
        clipboard.value = "selected text"

    reader = SystemSelectionReader(clipboard, copy_selection=copy_selection, timeout_sec=0.01, poll_sec=0)
    assert reader.read_text() == "selected text"
    assert clipboard.value == "original"


def test_selection_capture_failure_falls_back_safely() -> None:
    clipboard = Clipboard("original")
    reader = SystemSelectionReader(
        clipboard,
        copy_selection=lambda: (_ for _ in ()).throw(RuntimeError("copy failed")),
        timeout_sec=0.01,
        poll_sec=0,
    )
    assert reader.read_text() == ""
    assert clipboard.value == "original"

