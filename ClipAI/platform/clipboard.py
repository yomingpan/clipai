from __future__ import annotations

from io import BytesIO

import pyperclip

from ClipAI.core.errors import InputError
from ClipAI.core.models import ImageContent

MAX_CLIPBOARD_IMAGE_BYTES = 20 * 1024 * 1024


class SystemClipboard:
    def read_image(self) -> ImageContent | None:
        try:
            from PIL import Image, ImageGrab

            value = ImageGrab.grabclipboard()
            if not isinstance(value, Image.Image):
                return None
            buffer = BytesIO()
            value.convert("RGB").save(buffer, format="PNG", optimize=True)
            data = buffer.getvalue()
        except (OSError, ValueError) as exc:
            raise InputError("Clipboard image could not be decoded.") from exc
        if len(data) > MAX_CLIPBOARD_IMAGE_BYTES:
            raise InputError("Clipboard image is too large. Copy a smaller image and try again.")
        return ImageContent(data=data, mime_type="image/png")

    def read_text(self) -> str:
        value = pyperclip.paste()
        return "" if value is None else str(value)

    def write_text(self, text: str) -> None:
        pyperclip.copy(text)
