from __future__ import annotations

from ClipAI.core.errors import InputError
from ClipAI.core.models import InputDocument, InputMode
from ClipAI.core.ports import ClipboardReader, SelectionReader


class InputResolver:
    def __init__(self, clipboard: ClipboardReader, selection: SelectionReader | None = None) -> None:
        self._clipboard = clipboard
        self._selection = selection

    def resolve(self, mode: InputMode) -> InputDocument:
        image = self._clipboard.read_image() if hasattr(self._clipboard, "read_image") else None
        if image is not None:
            return InputDocument(text="", source="clipboard", image=image)
        if mode == "selection_or_clipboard" and self._selection is not None:
            selected = self._selection.read_text().strip()
            if selected:
                return InputDocument(text=selected, source="selection")
        clipboard_text = self._clipboard.read_text().strip()
        if not clipboard_text:
            raise InputError("No text found. Select or copy text, then trigger ClipAI again.")
        return InputDocument(text=clipboard_text, source="clipboard")
