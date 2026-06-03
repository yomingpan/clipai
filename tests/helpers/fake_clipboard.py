from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class FakeClipboard:
    text: str = ""
    image: Any | None = None

    def read_text(self, *args, **kwargs) -> str:
        del args, kwargs
        return self.text

    def write_text(self, text: str, *args, **kwargs) -> None:
        del args, kwargs
        self.text = text

    def read_image(self, *args, **kwargs):
        del args, kwargs
        return self.image

    def clear(self) -> None:
        self.text = ""
        self.image = None
