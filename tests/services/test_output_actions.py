from __future__ import annotations

import pytest

from ClipAI.services.output_actions import OutputActions
from ClipAI.core.models import ClipboardSnapshot, PasteTarget
from ClipAI.services.speech_text import SpeechTextPreprocessor


class Clipboard:
    def __init__(self, text: str) -> None:
        self.text = text
        self.writes: list[str] = []
        self.sequence = 0

    def read_text(self) -> str:
        return self.text

    def write_text(self, text: str) -> None:
        self.text = text
        self.writes.append(text)
        self.sequence += 1

    def read_image(self):
        return None

    def snapshot(self) -> ClipboardSnapshot:
        return ClipboardSnapshot(self.text)

    def sequence_number(self) -> int:
        return self.sequence

    def restore_if_unchanged(self, snapshot: ClipboardSnapshot, expected_sequence: int) -> bool:
        if self.sequence != expected_sequence:
            return False
        self.write_text(snapshot.text)
        return True


class Keyboard:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def paste(self, target: PasteTarget) -> None:
        assert target == TARGET
        self.calls += 1
        if self.fail:
            raise RuntimeError("paste failed")


TARGET = PasteTarget("hwnd:10", 42, "Notepad", "Untitled", 1)


def test_paste_restores_clipboard_after_focus_delay() -> None:
    clipboard = Clipboard("original")
    keyboard = Keyboard()
    waits: list[float] = []
    actions = OutputActions(clipboard=clipboard, keyboard=keyboard, wait=waits.append, paste_restore_delay_sec=0.25)
    actions.paste("result", TARGET)
    assert clipboard.writes == ["result", "original"]
    assert keyboard.calls == 1
    assert waits == [0.25]


def test_paste_restores_clipboard_when_keyboard_fails() -> None:
    clipboard = Clipboard("original")
    actions = OutputActions(clipboard=clipboard, keyboard=Keyboard(fail=True), wait=lambda _delay: None)
    with pytest.raises(RuntimeError, match="paste failed"):
        actions.paste("result", TARGET)
    assert clipboard.text == "original"


def test_speech_text_removes_markdown_noise_but_preserves_meaning() -> None:
    text = "# **Title**\n* Use C++ at 12.5%.\n[OpenAI](https://openai.com) don't stop.\n```py\nprint('*')\n```"
    assert SpeechTextPreprocessor().prepare(text) == "Title\nUse C++ at 12.5%.\nOpenAI don't stop."


def test_paste_does_not_restore_over_newer_clipboard_content() -> None:
    clipboard = Clipboard("original")

    def external_update(_delay: float) -> None:
        clipboard.write_text("new user content")

    OutputActions(clipboard=clipboard, keyboard=Keyboard(), wait=external_update).paste("result", TARGET)
    assert clipboard.text == "new user content"
