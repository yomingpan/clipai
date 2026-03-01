from __future__ import annotations

import pyperclip


def read_text() -> str:
    try:
        return pyperclip.paste() or ""
    except Exception:
        return ""


def read_image_base64() -> str | None:
    return None


def write_text(text: str) -> None:
    pyperclip.copy(text)
