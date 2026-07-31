from __future__ import annotations

from ClipAI.core.errors import InputError
from ClipAI.core.models import InputDocument, InputMode
from ClipAI.core.ports import ClipboardReader, SelectionReader
from ClipAI.core.state import CancellationToken


class InputResolver:
    def __init__(self, clipboard: ClipboardReader, selection: SelectionReader | None = None) -> None:
        self._clipboard = clipboard
        self._selection = selection

    def resolve(self, mode: InputMode, cancellation: CancellationToken | None = None) -> InputDocument:
        if mode == "clipboard_image":
            image = self._clipboard.read_image()
            if image is None:
                raise InputError("No screenshot found. Copy a screenshot to the clipboard, then trigger ClipAI again.")
            return InputDocument(text="", source="screenshot", image=image)
        if mode == "selection_or_clipboard" and self._selection is not None:
            selected = self._selection.read_text(cancellation).strip()
            if selected:
                return InputDocument(text=selected, source="selection")
        image = self._clipboard.read_image()
        if image is not None:
            return InputDocument(text="", source="clipboard", image=image)
        clipboard_text = self._clipboard.read_text().strip()
        if not clipboard_text:
            raise InputError("No text found. Select or copy text, then trigger ClipAI again.")
        return InputDocument(text=clipboard_text, source="clipboard")
