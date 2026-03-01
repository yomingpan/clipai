from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class InputSnapshot:
    text: str
    image_base64: str | None


class InputReceiver:
    def __init__(self, read_text: Callable[[], str], read_image_b64: Callable[[], str | None]) -> None:
        self._read_text = read_text
        self._read_image_b64 = read_image_b64

    def collect(self) -> InputSnapshot:
        return InputSnapshot(text=self._read_text(), image_base64=self._read_image_b64())
