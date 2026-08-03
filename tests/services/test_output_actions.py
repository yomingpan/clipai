from __future__ import annotations

from ClipAI.services.output_actions import OutputActions
from ClipAI.services.speech_text import SpeechTextPreprocessor


class Clipboard:
    def __init__(self, text: str) -> None:
        self.text = text
        self.writes: list[str] = []

    def read_text(self) -> str:
        return self.text

    def write_text(self, text: str) -> None:
        self.text = text
        self.writes.append(text)

    def read_image(self):
        return None


def test_copy_writes_canonical_text() -> None:
    clipboard = Clipboard("original")
    OutputActions(clipboard=clipboard).copy("result")
    assert clipboard.writes == ["result"]


def test_speech_text_removes_markdown_noise_but_preserves_meaning() -> None:
    text = "# **Title**\n* Use C++ at 12.5%.\n[OpenAI](https://openai.com) don't stop.\n```py\nprint('*')\n```"
    assert SpeechTextPreprocessor().prepare(text) == "Title\nUse C++ at 12.5%.\nOpenAI don't stop."
