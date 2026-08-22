import pytest

from ClipAI.core.models import ImageContent, ResolvedAction
from ClipAI.core.errors import InputError
from ClipAI.providers.anthropic import AnthropicProvider
from ClipAI.providers.gemini import GeminiProvider
from ClipAI.providers.openai import OpenAIProvider
from ClipAI.services.input_resolver import InputResolver
from ClipAI.services.prompt_builder import PromptBuilder


class Clipboard:
    def __init__(self, image=None, text="clipboard"):
        self.image = image
        self.text = text

    def read_image(self):
        return self.image

    def read_text(self):
        return self.text


class Selection:
    def read_text(self, cancellation=None):
        return "selected"


def action():
    return ResolvedAction("a", "A", "system", "Analyze: {input}", "short", "selection_or_clipboard", "popup", 0.2)


def request():
    image = ImageContent(b"png", "image/png")
    return PromptBuilder().build(action(), "", image=image, model="m", default_temperature=0.2)


def test_selection_wins_over_clipboard_image_and_text():
    image = ImageContent(b"png", "image/png")
    document = InputResolver(Clipboard(image), Selection()).resolve("selection_or_clipboard")
    assert document.image is None
    assert document.text == "selected"
    assert document.source == "selection"


def test_clipboard_image_wins_over_clipboard_text_without_selection():
    image = ImageContent(b"png", "image/png")
    selection = Selection()
    selection.read_text = lambda _cancellation=None: ""
    document = InputResolver(Clipboard(image), selection).resolve("selection_or_clipboard")
    assert document.image == image
    assert document.text == ""


def test_text_only_resolution_skips_clipboard_image_and_uses_clipboard_text():
    image = ImageContent(b"png", "image/png")
    selection = Selection()
    selection.read_text = lambda _cancellation=None: ""

    document = InputResolver(Clipboard(image=image, text="clipboard text"), selection).resolve_text()

    assert document == type(document)("clipboard text", "clipboard")


def test_clipboard_image_mode_requires_and_marks_a_screenshot():
    image = ImageContent(b"png", "image/png")

    document = InputResolver(Clipboard(image=image, text="not used"), Selection()).resolve("clipboard_image")

    assert document.image == image
    assert document.text == ""
    assert document.source == "screenshot"


def test_clipboard_image_mode_rejects_plain_text():
    with pytest.raises(InputError, match="No screenshot found"):
        InputResolver(Clipboard(image=None, text="plain text"), Selection()).resolve("clipboard_image")


def test_openai_multimodal_payload_uses_data_url():
    content = OpenAIProvider.to_payload(request())["input"][0]["content"]
    assert content[0] == {"type": "input_text", "text": "Analyze: "}
    assert content[1]["image_url"] == "data:image/png;base64,cG5n"


def test_gemini_multimodal_payload_uses_inline_data():
    parts = GeminiProvider.to_payload(request())["contents"][0]["parts"]
    assert parts[1]["inline_data"] == {"mime_type": "image/png", "data": "cG5n"}


def test_anthropic_multimodal_payload_uses_base64_source():
    provider = object.__new__(AnthropicProvider)
    provider._settings = type("Settings", (), {"max_tokens": 100})()
    content = provider.to_payload(request())["messages"][0]["content"]
    assert content[1]["source"] == {"type": "base64", "media_type": "image/png", "data": "cG5n"}
