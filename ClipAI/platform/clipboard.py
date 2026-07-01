from __future__ import annotations

from typing import Protocol

import pyperclip


class ClipboardGateway(Protocol):
    def read_text(self) -> str:
        ...

    def write_text(self, text: str) -> None:
        ...


class SystemClipboard:
    def read_text(self) -> str:
        value = pyperclip.paste()
        return "" if value is None else str(value)

    def write_text(self, text: str) -> None:
        pyperclip.copy(text)
